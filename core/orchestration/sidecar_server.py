"""
Servidor Sidecar (resolución de la deuda D14)
=============================================

Expone por HTTP local lo único que el proceso Rust no puede resolver por su
cuenta: ejecutar el grafo LangGraph y buscar sobre LanceDB. Todo lo demás
—el feed, el tablero, la telemetría— lo lee Rust directamente de PostgreSQL,
porque abrir el dashboard no debería cruzar dos procesos para hacer un
SELECT.

    POST /api/scan     ejecuta el pipeline y, si procede, lo persiste
    POST /api/search   búsqueda híbrida densa + BM25 con fusión RRF
    GET  /api/health   estado del proceso y de los modelos cargados

Dos decisiones de seguridad
---------------------------
1. **Solo loopback.** El servidor escucha en 127.0.0.1. Un sidecar de
   escritorio no tiene ningún motivo para ser alcanzable desde la red.
2. **Token opcional.** Incluso en loopback, cualquier proceso del equipo
   puede llamar a `/api/scan`, que consume cuota de la API de Reddit. Si
   `RIR_SIDECAR_TOKEN` está definido, se exige en cada petición.

Ejecución:

    python -m core.orchestration.sidecar_server
    python -m core.orchestration.sidecar_server --port 9000
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from .graph import RadarDependencies
from .pipeline import RadarPipeline, create_default_dependencies

logger = logging.getLogger(__name__)

# Loopback a propósito: ver la nota de seguridad de arriba.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

PORT_ENV_VAR = "RIR_SIDECAR_PORT"
TOKEN_ENV_VAR = "RIR_SIDECAR_TOKEN"
TOKEN_HEADER = "X-Radar-Token"

SERVICE_NAME = "reddit-intelligence-radar-sidecar"
SERVICE_VERSION = "0.1.0"


# =====================================================================
# Contratos
# =====================================================================

class ScanRequest(BaseModel):
    subreddit: str
    limit: int = Field(default=25, ge=1, le=100)
    sort: str = Field(default="hot")
    persist: Optional[bool] = None
    # Quien invoca puede fijar el identificador. Sin eso no hay forma de
    # cancelar un escaneo que todavia no ha empezado a responder.
    runId: Optional[str] = None

    @field_validator("subreddit")
    @classmethod
    def _subreddit_not_blank(cls, value: str) -> str:
        cleaned = (value or "").strip().removeprefix("r/").removeprefix("/")
        if not cleaned:
            raise ValueError("El subreddit no puede estar vacio")
        return cleaned


class SearchRequest(BaseModel):
    query: str
    min_score: float = Field(default=0.0, alias="minScore", ge=0.0, le=100.0)
    limit: int = Field(default=10, ge=1, le=100)

    model_config = {"populate_by_name": True}

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("La consulta no puede estar vacia")
        return value


class ModeRequest(BaseModel):
    mode: Literal["synthetic", "reddit"]


class CredentialsRequest(BaseModel):
    clientId: str
    clientSecret: str
    userAgent: str = "python:reddit-intelligence-radar:v0.5"
    username: Optional[str] = None
    password: Optional[str] = None

    @field_validator("clientId", "clientSecret")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("No puede estar vacio")
        return value.strip()


class BlueprintRequest(BaseModel):
    """Peticion de especificacion de proyecto.

    El cluster viaja entero en el cuerpo en lugar de por clave: quien lo pide
    (el puente de Rust) ya lo ha leido de PostgreSQL, y volver a consultarlo
    aqui abriria una segunda fuente de verdad que podria discrepar.
    """

    cluster: Dict[str, Any] = Field(default_factory=dict)
    language: str = "es"


class GeminiRequest(BaseModel):
    """Clave y modelo del motor de arquitectura."""

    apiKey: str = ""
    model: str = "gemini-2.5-pro"


class ArchitectRequest(BaseModel):
    """Peticion de arquitectura para un cluster.

    Igual que el blueprint, el cluster viaja entero: quien lo pide ya lo leyo
    de PostgreSQL.
    """

    cluster: Dict[str, Any] = Field(default_factory=dict)
    language: str = "es"


class ProbeResponse(BaseModel):
    ok: bool
    detail: str


class CancelRequest(BaseModel):
    runId: str


class CancelResponse(BaseModel):
    runId: str
    # False si no habia ningun escaneo con ese id en marcha. No es un error:
    # puede ser una cancelacion anticipada, o llegar tarde.
    wasActive: bool


class ScanResponse(BaseModel):
    subreddit: str
    runId: Optional[str] = None
    cycles: int = 0
    stats: Dict[str, int] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    qualified: List[Dict[str, Any]] = Field(default_factory=list)
    clusters: List[Dict[str, Any]] = Field(default_factory=list)
    qualifiedClusters: List[Dict[str, Any]] = Field(default_factory=list)
    persisted: bool = False
    # Por que no se persistio. Tragarse el motivo convertia un fallo de base
    # de datos en un silencioso "persisted: false" imposible de diagnosticar.
    persistError: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    hits: List[Dict[str, Any]] = Field(default_factory=list)


# =====================================================================
# Aplicación
# =====================================================================

def create_app(
    deps: Optional[RadarDependencies] = None,
    token: Optional[str] = None,
    persist_default: bool = True,
    postgres_dsn: Optional[str] = None,
    env_path: Optional[str] = None,
) -> FastAPI:
    """
    Construye la aplicación sobre unas dependencias dadas.

    Args:
        deps: colaboradores del grafo. Si se omiten, se crean los de
            producción (ingesta real contra Reddit, almacén real).
        token: si se indica, cada petición debe traerlo en `X-Radar-Token`.
        persist_default: si los escaneos vuelcan a PostgreSQL por defecto.
        postgres_dsn: cadena de conexión para esa persistencia.
        env_path: archivo de configuración que gestiona la vista de ajustes.
    """
    started_at = time.monotonic()
    dependencies = deps or create_default_dependencies()
    pipeline = RadarPipeline(deps=dependencies)

    app = FastAPI(
        title=SERVICE_NAME,
        version=SERVICE_VERSION,
        docs_url=None,       # sin documentación interactiva: no es una API pública
        redoc_url=None,
        openapi_url=None,
    )

    # Escaneos en marcha y cancelaciones pendientes. Un dict basta: FastAPI
    # atiende sobre un unico bucle de eventos, sin concurrencia real entre
    # estas lecturas y escrituras.
    active_runs: set = set()
    cancelled_runs: set = set()

    def require_token(
        x_radar_token: Optional[str] = Header(default=None, alias=TOKEN_HEADER),
    ) -> None:
        if token and x_radar_token != token:
            raise HTTPException(status_code=401, detail="Token invalido o ausente")

    # -- Salud ---------------------------------------------------------

    @app.get("/api/health", dependencies=[Depends(require_token)])
    def health() -> Dict[str, Any]:
        """
        Estado del proceso y de los modelos realmente cargados.

        Informa del motor de clasificación efectivo, no del deseado: mientras
        el NLI corra en su modo heurístico, quien consulte esto debe poder
        saberlo.
        """
        embedder = getattr(dependencies.store, "embedder", None)
        store_records = _safe(lambda: dependencies.store.count_records(), -1)

        classifier = "heuristic"
        nli_available = False
        engine = dependencies.engine  # sin forzar su construcción
        if engine is not None:
            nli_available = getattr(engine.zeroshot_classifier, "hf_pipeline", None) is not None
            classifier = "transformers" if nli_available else "heuristic"

        return {
            "status": "ok",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "uptimeSeconds": round(time.monotonic() - started_at, 3),
            "embedder": {
                "name": getattr(embedder, "name", "desconocido"),
                "semantic": bool(getattr(embedder, "is_semantic", False)),
                "dim": int(getattr(embedder, "dim", 0) or 0),
            },
            "nli": {
                "engine": classifier,
                "available": nli_available,
                "loaded": engine is not None,
            },
            "store": {
                "path": str(getattr(dependencies.store, "db_path", "")),
                "records": store_records,
            },
            "persistence": {
                "enabled": persist_default,
                "target": "postgresql" if persist_default else None,
            },
        }

    # -- Escaneo -------------------------------------------------------

    @app.post("/api/scan", response_model=ScanResponse,
              dependencies=[Depends(require_token)])
    async def scan(request: ScanRequest) -> ScanResponse:
        """
        Ejecuta el pipeline completo y, si procede, lo persiste.

        Los errores de un nodo concreto (una página que no descarga, un
        análisis que falla) viajan en `errors` y no tumban la petición: el
        grafo está diseñado para degradar la cosecha, no para abortarla.
        """
        try:
            # Se pide el estado COMPLETO, no el resumen: persistir necesita
            # `signals` y `filtered_items`, que el resumen descarta.
            final_state = await pipeline.arun_state(
                subreddit=request.subreddit,
                limit=request.limit,
                sort=request.sort,
            )
        except Exception as exc:
            logger.exception("Fallo ejecutando el pipeline")
            raise HTTPException(status_code=500, detail=f"Fallo del pipeline: {exc}")

        should_persist = persist_default if request.persist is None else request.persist
        run_id: Optional[str] = None
        persisted = False
        persist_error: Optional[str] = None

        if should_persist:
            run_id, persisted, persist_error = await _persist(
                final_state, dependencies, postgres_dsn
            )

        result = pipeline.summarize(final_state)

        return ScanResponse(
            subreddit=request.subreddit,
            runId=run_id,
            cycles=int(result.get("cycles", 0)),
            stats=dict(result.get("stats") or {}),
            errors=list(result.get("errors") or []),
            qualified=list(result.get("qualified") or []),
            clusters=list(result.get("clusters") or []),
            qualifiedClusters=list(result.get("qualified_clusters") or []),
            persisted=persisted,
            persistError=persist_error,
        )


    def _forget(run_id: str) -> None:
        """
        Olvida un escaneo terminado.

        Sin esto, reutilizar un identificador cancelado haria que el
        siguiente escaneo con ese id naciera muerto.
        """
        active_runs.discard(run_id)
        cancelled_runs.discard(run_id)

    # -- Configuracion -------------------------------------------------

    # El modo vive en una lista de un elemento porque los closures de Python
    # no pueden reasignar una variable del ambito exterior sin `nonlocal`, y
    # aqui hay varios manejadores que la tocan.
    mode_holder = ["reddit" if _is_reddit_fetcher(dependencies.fetcher) else "synthetic"]

    def _gemini_summary() -> Dict[str, Any]:
        """Estado del motor de arquitectura, SIN devolver la clave.

        Vale lo mismo que para el secreto de Reddit: una clave que llega al
        frontend acaba en una captura o en el inspector.
        """
        from core.intelligence.gemini_architect import MODELO_POR_DEFECTO

        values = load_dotenv(env_path, env={})
        key = (values.get("RIR_GEMINI_API_KEY") or "").strip()
        model = (values.get("RIR_GEMINI_MODEL") or "").strip() or MODELO_POR_DEFECTO

        masked = ""
        if key:
            masked = key[:6] + "…" + key[-4:] if len(key) > 12 else "…"

        return {"configured": bool(key), "keyMasked": masked, "model": model}

    def _credentials_summary() -> Dict[str, Any]:
        """
        Estado de las credenciales SIN devolver el secreto.

        Un secreto que viaja al frontend acaba en el log de alguien, en una
        captura de pantalla o en el inspector del navegador.
        """
        values = load_dotenv(env_path, env={})
        client_id = (values.get("RIR_REDDIT_CLIENT_ID") or "").strip()
        secret = (values.get("RIR_REDDIT_CLIENT_SECRET") or "").strip()

        masked = ""
        if client_id:
            masked = (
                client_id[:4] + "\u2026" + client_id[-2:]
                if len(client_id) > 6
                else "\u2026"
            )

        return {
            "configured": bool(client_id and secret),
            "clientIdMasked": masked,
            "userAgent": (values.get("RIR_REDDIT_USER_AGENT") or "").strip(),
            "hasUser": bool((values.get("RIR_REDDIT_USERNAME") or "").strip()),
        }

    @app.get("/api/config", dependencies=[Depends(require_token)])
    def get_config() -> Dict[str, Any]:
        """Lo que la vista de Configuracion necesita saber."""
        return {
            "fetcherMode": mode_holder[0],
            "credentials": _credentials_summary(),
            "envPath": str(env_path or _default_env_path()),
            "syntheticPosts": synthetic_total(),
            "gemini": _gemini_summary(),
        }

    @app.post("/api/config/mode", dependencies=[Depends(require_token)])
    def set_mode(request: ModeRequest) -> Dict[str, Any]:
        """
        Cambia la fuente de datos en caliente.

        Los nodos leen `deps.fetcher` en cada llamada, asi que basta con
        sustituirlo: no hace falta reconstruir el grafo ni reiniciar nada.
        """
        if request.mode == "synthetic":
            from core.ingestion.synthetic import SyntheticFetcher

            dependencies.fetcher = SyntheticFetcher()
        else:
            from .pipeline import RedditFetcher

            dependencies.fetcher = RedditFetcher()

        mode_holder[0] = request.mode
        logger.info("Fuente de datos cambiada a '%s'", request.mode)
        return {"fetcherMode": request.mode}

    @app.post("/api/credentials", dependencies=[Depends(require_token)])
    def save_credentials(request: CredentialsRequest) -> Dict[str, Any]:
        """
        Guarda las credenciales en el `.env`.

        Se actualizan solo las claves de Reddit: el archivo suele tener mas
        cosas (la conexion a PostgreSQL, rutas) y perderlas seria peor que
        no poder guardar.
        """
        values = {
            "RIR_REDDIT_CLIENT_ID": request.clientId,
            "RIR_REDDIT_CLIENT_SECRET": request.clientSecret,
            "RIR_REDDIT_USER_AGENT": request.userAgent,
        }
        if request.username:
            values["RIR_REDDIT_USERNAME"] = request.username
        if request.password:
            values["RIR_REDDIT_PASSWORD"] = request.password

        target = update_dotenv(values, env_path)
        # Se registra que se guardo, nunca lo guardado.
        logger.info("Credenciales de Reddit actualizadas en %s", target)
        return {"saved": True, "envPath": str(target),
                "credentials": _credentials_summary()}

    @app.post("/api/credentials/test", response_model=ProbeResponse,
              dependencies=[Depends(require_token)])
    async def test_credentials() -> ProbeResponse:
        """Intenta obtener un token real con lo que hay guardado."""
        from core.ingestion.auth import RedditOAuth

        values = load_dotenv(env_path, env={})
        auth = RedditOAuth.from_env(env=values)
        if auth is None:
            return ProbeResponse(
                ok=False,
                detail="Faltan credenciales: guarda el Client ID y el Secret primero.",
            )

        ok, detail = await _probe_reddit(auth)
        return ProbeResponse(ok=ok, detail=detail)

    # -- Cancelacion ---------------------------------------------------

    @app.post("/api/scan/cancel", response_model=CancelResponse,
              dependencies=[Depends(require_token)])
    def cancel(request: CancelRequest) -> CancelResponse:
        """
        Solicita la interrupcion de un escaneo.

        Es cooperativa: el grafo se corta ENTRE nodos, nunca a mitad de uno.
        Abortar un nodo a media escritura dejaria el almacen inconsistente,
        y lo cosechado hasta ese punto es valido y merece conservarse.

        Se admite cancelar un id que aun no ha arrancado: quien lanza el
        escaneo puede fijar el suyo, y entre la peticion y el primer nodo
        hay tiempo de sobra para arrepentirse.
        """
        was_active = request.runId in active_runs
        cancelled_runs.add(request.runId)
        logger.info(
            "Cancelacion solicitada para %s (activo=%s)", request.runId, was_active
        )
        return CancelResponse(runId=request.runId, wasActive=was_active)

    # -- Escaneo con progreso en vivo -----------------------------------

    @app.post("/api/scan/stream", dependencies=[Depends(require_token)])
    async def scan_stream(request: ScanRequest) -> StreamingResponse:
        """
        Igual que `/api/scan`, pero emitiendo el avance nodo a nodo por SSE.

        Un escaneo puede durar minutos. Sin esto, la interfaz solo puede
        sondear, que es ruido para todas las capas y llega tarde igual.

        El `runId` se genera al abrir el flujo y viaja en todos los eventos:
        sin un identificador estable no se pueden correlacionar. El id de la
        ejecución en PostgreSQL, que solo existe tras persistir, viaja
        aparte en el evento final.
        """
        run_id = request.runId or str(uuid.uuid4())
        should_persist = persist_default if request.persist is None else request.persist

        async def emitir():
            active_runs.add(run_id)
            yield _sse({
                "type": "run:started",
                "runId": run_id,
                "subreddit": request.subreddit,
            })

            final_state: Dict[str, Any] = {}
            cancelled = run_id in cancelled_runs
            try:
                if not cancelled:
                    async for kind, payload in pipeline.astream_state(
                        subreddit=request.subreddit,
                        limit=request.limit,
                        sort=request.sort,
                    ):
                        if kind == "node":
                            state = payload["state"]
                            final_state = state
                            yield _sse({
                                "type": "run:progress",
                                "runId": run_id,
                                "node": payload["node"],
                                "cycle": int(state.get("cycle", 0)) or 1,
                                "stats": dict(state.get("stats") or {}),
                            })
                            # Se comprueba ENTRE nodos: cortar a mitad de uno
                            # dejaria el almacen a medio escribir.
                            if run_id in cancelled_runs:
                                cancelled = True
                                break
                        else:
                            final_state = payload or {}
            except Exception as exc:
                logger.exception("Fallo ejecutando el pipeline en streaming")
                _forget(run_id)
                yield _sse({
                    "type": "run:error",
                    "runId": run_id,
                    "message": f"{type(exc).__name__}: {exc}",
                })
                return

            persisted_run_id = None
            persist_error = None
            if should_persist and final_state:
                # Un escaneo cancelado conserva lo cosechado, marcado como
                # tal: media cosecha sigue siendo informacion.
                persisted_run_id, _, persist_error = await _persist(
                    final_state,
                    dependencies,
                    postgres_dsn,
                    status="cancelled" if cancelled else "completed",
                )

            result = pipeline.summarize(final_state)
            _forget(run_id)
            yield _sse({
                "type": "run:cancelled" if cancelled else "run:finished",
                "runId": run_id,
                "persistedRunId": persisted_run_id,
                "persistError": persist_error,
                "qualified": len(result.get("qualified") or []),
                "clusters": len(result.get("qualified_clusters") or []),
                "stats": dict(result.get("stats") or {}),
                "errors": list(result.get("errors") or []),
            })

        return StreamingResponse(
            emitir(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                # Sin esto, un proxy intermedio podria retener el flujo y
                # entregarlo de golpe al final, que es justo lo contrario.
                "X-Accel-Buffering": "no",
            },
        )

    # -- Motor de arquitectura (Gemini) --------------------------------

    def _gemini_credenciales() -> tuple:
        from core.intelligence.gemini_architect import MODELO_POR_DEFECTO

        values = load_dotenv(env_path, env={})
        key = (values.get("RIR_GEMINI_API_KEY") or "").strip()
        model = (values.get("RIR_GEMINI_MODEL") or "").strip() or MODELO_POR_DEFECTO
        return key, model

    @app.post("/api/gemini", dependencies=[Depends(require_token)])
    def save_gemini(request: GeminiRequest) -> Dict[str, Any]:
        """Guarda la clave en el `.env` del proyecto."""
        if not request.apiKey.strip():
            raise HTTPException(status_code=400, detail="La clave no puede estar vacia")

        update_dotenv(
            {
                "RIR_GEMINI_API_KEY": request.apiKey.strip(),
                "RIR_GEMINI_MODEL": request.model.strip(),
            },
            env_path,
        )
        logger.info("Clave de Gemini guardada (modelo %s)", request.model)
        return {"gemini": _gemini_summary()}

    @app.post("/api/gemini/test", response_model=ProbeResponse,
              dependencies=[Depends(require_token)])
    def test_gemini() -> ProbeResponse:
        from core.intelligence import gemini_architect

        key, model = _gemini_credenciales()
        ok, detalle = gemini_architect.probe_api_key(key, model=model)
        return ProbeResponse(ok=ok, detail=detalle)

    @app.post("/api/architect/generate", dependencies=[Depends(require_token)])
    def architect_generate(request: ArchitectRequest) -> StreamingResponse:
        """
        Pide el plan de arquitectura y lo va sirviendo segun llega.

        Se responde en texto plano por trozos y no de una vez: con un modelo
        de razonamiento el documento tarda, y quien mira una pantalla quieta
        da la aplicacion por colgada.
        """
        from core.intelligence import gemini_architect

        key, model = _gemini_credenciales()
        if not key:
            raise HTTPException(
                status_code=412,
                detail="No hay clave de Gemini guardada. Se configura en Ajustes.",
            )

        def cuerpo():
            try:
                for trozo in gemini_architect.stream_architecture(
                    request.cluster,
                    api_key=key,
                    model=model,
                    language=request.language,
                ):
                    yield trozo
            except Exception as exc:
                # El fallo llega a mitad del texto ya enviado: no se puede
                # cambiar el codigo de estado, asi que se escribe dentro del
                # documento, donde quien lo lee lo va a ver.
                logger.exception("Fallo generando la arquitectura")
                yield f"\n\n> **Error del motor de arquitectura:** {exc}\n"

        return StreamingResponse(cuerpo(), media_type="text/plain; charset=utf-8")

    # -- Especificacion de proyecto ------------------------------------

    @app.post("/api/blueprint", dependencies=[Depends(require_token)])
    def blueprint(request: BlueprintRequest) -> Dict[str, Any]:
        """
        Sintetiza el PRD de un cluster.

        La sintesis es determinista y no toca disco ni red, asi que responde
        en el mismo hilo: no hay nada que esperar.
        """
        from core.intelligence.blueprint import build_blueprint

        return build_blueprint(request.cluster, request.language).to_dict()

    # -- Búsqueda ------------------------------------------------------

    @app.post("/api/search", response_model=SearchResponse,
              dependencies=[Depends(require_token)])
    def search(request: SearchRequest) -> SearchResponse:
        filter_sql = (
            f"opportunity_score >= {float(request.min_score)}"
            if request.min_score
            else None
        )
        try:
            results = dependencies.get_search_engine().search(
                request.query, limit=request.limit, filter_sql=filter_sql
            )
        except Exception as exc:
            logger.exception("Fallo en la busqueda hibrida")
            raise HTTPException(status_code=500, detail=f"Fallo de busqueda: {exc}")

        return SearchResponse(
            query=request.query,
            hits=[_hit_to_camel(hit) for hit in results],
        )

    return app


# =====================================================================
# Auxiliares
# =====================================================================

def _default_env_path() -> str:
    """Ruta del `.env` del proyecto."""
    from pathlib import Path

    return str(Path(__file__).resolve().parents[2] / ".env")


def _is_reddit_fetcher(fetcher: Any) -> bool:
    return type(fetcher).__name__ == "RedditFetcher"


def synthetic_total() -> int:
    from core.ingestion.synthetic import total_posts

    return total_posts()


def load_dotenv(path: Optional[str], env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Lee un `.env` sin tocar el entorno del proceso."""
    from core.ingestion.auth import load_dotenv as _load

    return _load(path or _default_env_path(), env=env if env is not None else {})


def update_dotenv(values: Dict[str, str], path: Optional[str] = None):
    """
    Escribe o actualiza claves en un `.env`, preservando el resto.

    Se reescribe el archivo entero en lugar de anexar: anexar dejaria
    duplicados y la ultima linea ganaria en silencio.
    """
    from pathlib import Path

    target = Path(path or _default_env_path())
    target.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    if target.exists():
        lines = target.read_text(encoding="utf-8").splitlines()

    pending = dict(values)
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in pending:
                result.append(f"{key}={pending.pop(key)}")
                continue
        result.append(line)

    for key, value in pending.items():
        result.append(f"{key}={value}")

    target.write_text("\n".join(result) + "\n", encoding="utf-8")
    return target


async def _probe_reddit(auth) -> tuple:
    """
    Comprueba las credenciales pidiendo un token real.

    Se aisla en su propia funcion para poder sustituirla en las pruebas: un
    test que salga a Reddit no es un test, es una tirada de dados.
    """
    from core.ingestion.auth import RedditAuthError

    try:
        token = await auth.get_token()
        return True, f"Token obtenido correctamente ({len(token)} caracteres)."
    except RedditAuthError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _sse(payload: Dict[str, Any]) -> str:
    """Serializa un evento en el formato `text/event-stream`."""
    return "data: " + json.dumps(payload, default=str) + "\n\n"


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def _hit_to_camel(hit: Any) -> Dict[str, Any]:
    """Adapta un resultado de búsqueda al contrato de `ui/src/types/radar.ts`."""
    return {
        "id": hit.id,
        "text": hit.text,
        "subreddit": hit.subreddit,
        "author": hit.author,
        "opportunityScore": hit.opportunity_score,
        "urgencyTier": hit.urgency_tier,
        "jobStatement": hit.job_statement,
        "currentSolution": hit.current_solution,
        "rrfScore": hit.rrf_score,
        "denseRank": hit.dense_rank,
        "bm25Rank": hit.bm25_rank,
        "bm25Score": hit.bm25_score,
    }


async def _persist(
    state: Dict[str, Any],
    deps: RadarDependencies,
    postgres_dsn: Optional[str],
    status: str = "completed",
) -> tuple[Optional[str], bool, Optional[str]]:
    """
    Vuelca el estado final en PostgreSQL.

    Corre en un hilo aparte a proposito. uvicorn impone un
    `ProactorEventLoop` en Windows y psycopg se niega a funcionar sobre el;
    `run_async` levanta un `SelectorEventLoop` propio en el hilo, que es
    compatible. Pelear con el bucle del servidor seria mas fragil que
    aislarse de el.

    Un fallo aqui no invalida el escaneo: los datos ya estan en LanceDB, asi
    que se informa del motivo y se sigue. Perder el rastro relacional es
    molesto; perder la cosecha, mucho peor.

    Returns:
        `(run_id, persistido, motivo_del_fallo)`.
    """
    import asyncio

    def _write() -> tuple[Optional[str], bool, Optional[str]]:
        try:
            from core.storage.postgres_store import PostgresStore, run_async

            embedder = getattr(deps.store, "embedder", None)

            async def _inner():
                async with PostgresStore(dsn=postgres_dsn) as store:
                    return await store.persist_state(
                        state,
                        trigger_source="sidecar",
                        embedding_model=getattr(embedder, "name", None),
                        status=status,
                    )

            summary = run_async(_inner())
            return summary.get("run_id"), True, None
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            logger.error("No se pudo persistir en PostgreSQL: %s", detail)
            return None, False, detail

    return await asyncio.to_thread(_write)


def run(
    host: str = DEFAULT_HOST,
    port: Optional[int] = None,
    token: Optional[str] = None,
    mode: str = "reddit",
) -> None:
    """
    Arranca el servidor con uvicorn.

    `mode` elige la fuente inicial. Se puede cambiar despues desde la
    interfaz sin reiniciar, pero arrancar ya en el modo correcto evita que
    el primer escaneo falle contra Reddit cuando lo que se queria era la
    demostracion.
    """
    import asyncio

    import uvicorn

    # psycopg no funciona sobre el ProactorEventLoop que Windows usa por
    # defecto. Aquí sí se cambia la política global, porque este es el punto
    # de entrada del proceso y no una importación lateral.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    port = port or int(os.environ.get(PORT_ENV_VAR, DEFAULT_PORT))
    token = token or os.environ.get(TOKEN_ENV_VAR)

    if not token:
        logger.warning(
            "Sidecar sin token: cualquier proceso local podra invocar /api/scan. "
            "Define %s para exigirlo.",
            TOKEN_ENV_VAR,
        )

    deps = None
    if mode == "synthetic":
        from core.ingestion.synthetic import SyntheticFetcher

        from .graph import RadarDependencies
        from core.storage import LanceDBStore

        store = LanceDBStore()
        deps = RadarDependencies(fetcher=SyntheticFetcher(), store=store)
        logger.info("Arrancando en modo DEMOSTRACION (corpus sintetico)")

    uvicorn.run(
        create_app(deps=deps, token=token), host=host, port=port, log_level="info"
    )


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Sidecar del Reddit Intelligence Radar")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument(
        "--mode",
        choices=["reddit", "synthetic"],
        default="reddit",
        help="fuente de datos inicial ('synthetic' usa el corpus de demostracion)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(host=args.host, port=args.port, mode=args.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
