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
2. **Token obligatorio (D-B).** Incluso en loopback, cualquier proceso del
   equipo podría llamar a `/api/scan`, que consume cuota de Reddit, o leer
   la configuración. La aplicación de escritorio genera un token aleatorio
   en cada arranque y lo pasa en `RIR_SIDECAR_TOKEN`; cada petición lo trae
   en `Authorization: Bearer`, y se compara en tiempo constante. Sin token
   el sidecar no arranca, salvo con `--insecure-dev` explícito.

Ejecución (la aplicación lo lanza sola; a mano, solo para desarrollo):

    RIR_SIDECAR_TOKEN=<64 hex> python -m core.orchestration.sidecar_server
    python -m core.orchestration.sidecar_server --insecure-dev --port 9000
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import sys
import time
import uuid
from collections.abc import Mapping, MutableMapping
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from .graph import RadarDependencies
from .pipeline import RadarPipeline, create_default_dependencies
from .source_status import SourceTracker

logger = logging.getLogger(__name__)

# Loopback a propósito: ver la nota de seguridad de arriba.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

PORT_ENV_VAR = "RIR_SIDECAR_PORT"
TOKEN_ENV_VAR = "RIR_SIDECAR_TOKEN"

#: Longitud mínima del token. El de la aplicación son 64 caracteres hex
#: (32 bytes aleatorios); uno corto se podría adivinar.
MIN_TOKEN_LENGTH = 32


class SidecarSinToken(RuntimeError):
    """El sidecar no puede servir sin token salvo con `--insecure-dev`."""


SERVICE_NAME = "reddit-intelligence-radar-sidecar"
SERVICE_VERSION = "0.1.0"


# =====================================================================
# Contratos
# =====================================================================

class ScanRequest(BaseModel):
    subreddit: str
    limit: int = Field(default=25, ge=1, le=100)
    sort: str = Field(default="hot")
    persist: bool | None = None
    # Quien invoca puede fijar el identificador. Sin eso no hay forma de
    # cancelar un escaneo que todavia no ha empezado a responder.
    runId: str | None = None

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
    username: str | None = None
    password: str | None = None

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

    cluster: dict[str, Any] = Field(default_factory=dict)
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

    cluster: dict[str, Any] = Field(default_factory=dict)
    language: str = "es"


class DocumentRequest(BaseModel):
    """Peticion del documento en PDF (AUD-008).

    El cluster llega entero, igual que para el blueprint. `architecture` es
    el Markdown del plan de Gemini si se genero en la sesion; si no, el
    documento lo declara «No generado».
    """

    cluster: dict[str, Any] = Field(default_factory=dict)
    language: str = "es"
    architecture: str | None = None


class TranslateRequest(BaseModel):
    """Tanda de citas a traducir.

    El limite esta para que una vista con muchas citas no dispare una peticion
    enorme al modelo por accidente.
    """

    texts: list[str] = Field(default_factory=list, max_length=60)
    target: str = "es"


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
    runId: str | None = None
    cycles: int = 0
    stats: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    qualified: list[dict[str, Any]] = Field(default_factory=list)
    clusters: list[dict[str, Any]] = Field(default_factory=list)
    qualifiedClusters: list[dict[str, Any]] = Field(default_factory=list)
    persisted: bool = False
    # Por que no se persistio. Tragarse el motivo convertia un fallo de base
    # de datos en un silencioso "persisted: false" imposible de diagnosticar.
    persistError: str | None = None
    # "completed" o "failed". Un escaneo sin acceso a la fuente es "failed"
    # con un codigo estable que la interfaz traduce (AUD-003).
    status: str = "completed"
    failureCode: str | None = None
    retryAfterSeconds: int | None = None
    # "demo" o "reddit", y el resultado Top N de la ejecucion (AUD-007).
    dataSource: str = "demo"
    top: dict[str, Any] | None = None


class SearchResponse(BaseModel):
    query: str
    hits: list[dict[str, Any]] = Field(default_factory=list)


# =====================================================================
# Aplicación
# =====================================================================

def create_app(
    deps: RadarDependencies | None = None,
    token: str | None = None,
    persist_default: bool = True,
    postgres_dsn: str | None = None,
    env_path: str | None = None,
    insecure_dev: bool = False,
) -> FastAPI:
    """
    Construye la aplicación sobre unas dependencias dadas.

    Args:
        deps: colaboradores del grafo. Si se omiten, se crean los de
            producción (ingesta real contra Reddit, almacén real).
        token: cada petición debe traerlo en `Authorization: Bearer`.
            Obligatorio, de al menos MIN_TOKEN_LENGTH caracteres.
        insecure_dev: permite servir sin token (desarrollo y tests que no
            prueban la seguridad). Hay que pedirlo explícitamente.
        persist_default: si los escaneos vuelcan a PostgreSQL por defecto.
        postgres_dsn: cadena de conexión para esa persistencia.
        env_path: archivo de configuración que gestiona la vista de ajustes.
    """
    if token is not None and len(token) < MIN_TOKEN_LENGTH:
        raise SidecarSinToken(f"El token debe tener al menos {MIN_TOKEN_LENGTH} caracteres.")
    if token is None and not insecure_dev:
        raise SidecarSinToken(
            f"Falta {TOKEN_ENV_VAR}. Solo con --insecure-dev puede servirse sin token."
        )

    started_at = time.monotonic()
    dependencies = deps or create_default_dependencies(env_path=env_path)
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

    # Lo que ha pasado de verdad contra Reddit (AUD-004). Alimenta el
    # indicador de la fuente: solo un 200 real lo pone en verde.
    fuente = SourceTracker()

    def _estado_fuente() -> dict[str, Any]:
        from core.ingestion.auth import load_reddit_oauth

        return fuente.snapshot(mode_holder[0], load_reddit_oauth(env_path) is not None)

    def _registrar_escaneo(es_reddit: bool, final_state: Mapping[str, Any]) -> None:
        """Anota el desenlace de un escaneo si lo sirvio Reddit.

        Solo un escaneo en modo Reddit que llego a descargar sin fallo es un
        200 real de la API OAuth: el corpus fabricado nunca verifica nada.
        """
        if not es_reddit:
            return
        failure = final_state.get("failure")
        if failure:
            fuente.record_failure(str(failure["code"]))
        elif int(final_state.get("cycle", 0) or 0) >= 1:
            fuente.record_success()

    def require_token(authorization: str | None = Header(default=None)) -> None:
        if token is None:
            return  # solo con insecure_dev, comprobado al construir la app
        esquema, _, valor = (authorization or "").partition(" ")
        # compare_digest tarda lo mismo acierte o falle en el primer
        # carácter: una comparación normal filtraría el token por tiempos.
        valido = hmac.compare_digest(valor.encode(), token.encode())
        if esquema != "Bearer" or not valido:
            raise HTTPException(
                status_code=401,
                detail="Token invalido o ausente",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # -- Salud ---------------------------------------------------------

    @app.get("/api/health", dependencies=[Depends(require_token)])
    def health() -> dict[str, Any]:
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
            "source": _estado_fuente(),
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
        es_reddit = _is_reddit_fetcher(dependencies.fetcher)
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
        run_id: str | None = None
        persisted = False
        persist_error: str | None = None
        failure = final_state.get("failure") or None
        status = "failed" if failure else "completed"
        _registrar_escaneo(es_reddit, final_state)

        fuente_datos = "reddit" if es_reddit else "demo"
        if should_persist:
            run_id, persisted, persist_error = await _persist(
                final_state, dependencies, postgres_dsn, status=status,
                data_source=fuente_datos,
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
            status=status,
            failureCode=failure["code"] if failure else None,
            retryAfterSeconds=failure.get("retryAfterSeconds") if failure else None,
            dataSource=fuente_datos,
            top=final_state.get("top"),
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

    def _gemini_summary() -> dict[str, Any]:
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

    def _credentials_summary() -> dict[str, Any]:
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
    def get_config() -> dict[str, Any]:
        """Lo que la vista de Configuracion necesita saber."""
        return {
            "fetcherMode": mode_holder[0],
            "credentials": _credentials_summary(),
            "envPath": str(env_path or _default_env_path()),
            "syntheticPosts": synthetic_total(),
            "gemini": _gemini_summary(),
        }

    @app.post("/api/config/mode", dependencies=[Depends(require_token)])
    def set_mode(request: ModeRequest) -> dict[str, Any]:
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

            dependencies.fetcher = RedditFetcher(env_path=env_path)

        mode_holder[0] = request.mode
        logger.info("Fuente de datos cambiada a '%s'", request.mode)
        return {"fetcherMode": request.mode}

    @app.post("/api/credentials", dependencies=[Depends(require_token)])
    def save_credentials(request: CredentialsRequest) -> dict[str, Any]:
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
        # El cliente construido con las credenciales anteriores ya no vale:
        # el siguiente escaneo lo rehace leyendo el `.env` recien escrito.
        invalidar = getattr(dependencies.fetcher, "invalidate", None)
        if callable(invalidar):
            invalidar()
        # Lo verificado era con las credenciales anteriores.
        fuente.reset()
        # Se registra que se guardo, nunca lo guardado.
        logger.info("Credenciales de Reddit actualizadas en %s", target)
        return {"saved": True, "envPath": str(target),
                "credentials": _credentials_summary()}

    @app.post("/api/credentials/test", response_model=ProbeResponse,
              dependencies=[Depends(require_token)])
    async def test_credentials() -> ProbeResponse:
        """Intenta obtener un token real con lo que hay guardado."""
        from core.ingestion.auth import load_reddit_oauth

        # La misma lectura que hace el escaneo: si aqui sale bien, el
        # escaneo usara exactamente estas credenciales.
        auth = load_reddit_oauth(env_path)
        if auth is None:
            return ProbeResponse(
                ok=False,
                detail="Faltan credenciales: guarda el Client ID y el Secret primero.",
            )

        ok, detail, code = await _probe_reddit(auth)
        if ok:
            fuente.record_success()
        else:
            fuente.record_failure(code or "reddit_auth_failed")
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

        es_reddit = _is_reddit_fetcher(dependencies.fetcher)

        async def emitir():
            active_runs.add(run_id)
            yield _sse({
                "type": "run:started",
                "runId": run_id,
                "subreddit": request.subreddit,
            })

            final_state: dict[str, Any] = {}
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
                    "code": "internal_error",
                    "message": f"{type(exc).__name__}: {exc}",
                    "retryAfterSeconds": None,
                    "persistedRunId": None,
                    "persistError": None,
                })
                return

            failure = final_state.get("failure") or None
            if not cancelled:
                _registrar_escaneo(es_reddit, final_state)
            if cancelled:
                status = "cancelled"
            elif failure:
                status = "failed"
            else:
                status = "completed"

            persisted_run_id = None
            persist_error = None
            if should_persist and final_state:
                # Un escaneo cancelado conserva lo cosechado, marcado como
                # tal: media cosecha sigue siendo informacion.
                persisted_run_id, _, persist_error = await _persist(
                    final_state,
                    dependencies,
                    postgres_dsn,
                    status=status,
                    data_source="reddit" if es_reddit else "demo",
                )

            result = pipeline.summarize(final_state)
            _forget(run_id)
            if failure and not cancelled:
                # La fuente no entrego datos: es un fallo, no una cosecha
                # vacia. El codigo es estable; la interfaz lo traduce.
                yield _sse({
                    "type": "run:error",
                    "runId": run_id,
                    "code": failure["code"],
                    "message": failure["message"],
                    "retryAfterSeconds": failure.get("retryAfterSeconds"),
                    "persistedRunId": persisted_run_id,
                    "persistError": persist_error,
                })
                return
            yield _sse({
                "type": "run:cancelled" if cancelled else "run:finished",
                "runId": run_id,
                "persistedRunId": persisted_run_id,
                "persistError": persist_error,
                "qualified": len(result.get("qualified") or []),
                "clusters": len(result.get("qualified_clusters") or []),
                "stats": dict(result.get("stats") or {}),
                "errors": list(result.get("errors") or []),
                "dataSource": "reddit" if es_reddit else "demo",
                "top": final_state.get("top"),
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

    # -- Traduccion de citas -------------------------------------------

    @app.post("/api/translate", dependencies=[Depends(require_token)])
    def translate_quotes(request: TranslateRequest) -> dict[str, Any]:
        """
        Traduce citas al idioma de la interfaz.

        Con clave de Gemini traduce el modelo; sin ella responde el motor sin
        conexion. Nunca devuelve error por esto: la vista tiene que poder
        pintar algo siempre, y una cita sin traducir se lee, un hueco no.
        """
        from core.intelligence import translator

        key, _modelo_guardado = _gemini_credenciales()
        traducciones = translator.translate(
            request.texts,
            request.target,
            api_key=key,
            # Traducir no necesita el razonamiento del Pro y se pide a menudo:
            # el modelo rapido cuesta menos y responde antes.
            model=translator.MODELO_POR_DEFECTO,
        )
        return {"translations": [t.to_dict() for t in traducciones]}

    # -- Motor de arquitectura (Gemini) --------------------------------

    def _gemini_credenciales() -> tuple:
        from core.intelligence.gemini_architect import MODELO_POR_DEFECTO

        values = load_dotenv(env_path, env={})
        key = (values.get("RIR_GEMINI_API_KEY") or "").strip()
        model = (values.get("RIR_GEMINI_MODEL") or "").strip() or MODELO_POR_DEFECTO
        return key, model

    @app.post("/api/gemini", dependencies=[Depends(require_token)])
    def save_gemini(request: GeminiRequest) -> dict[str, Any]:
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
        from core.intelligence.gemini_client import GeminiError, sanitize

        key, model = _gemini_credenciales()
        if not key:
            raise HTTPException(
                status_code=412,
                detail="No hay clave de Gemini guardada. Se configura en Ajustes.",
            )

        def evento(datos: dict[str, Any]) -> str:
            return json.dumps(datos, ensure_ascii=False) + "\n"

        def cuerpo():
            # Una linea JSON por evento (AUD-020): `chunk` con texto, y al
            # final `done` o `error`. El fallo llega a mitad del texto ya
            # enviado y no se puede cambiar el codigo de estado; antes se
            # escribia dentro del documento, que asi se daba por terminado.
            try:
                for trozo in gemini_architect.stream_architecture(
                    request.cluster,
                    api_key=key,
                    model=model,
                    language=request.language,
                ):
                    yield evento({"type": "chunk", "text": trozo})
            except GeminiError as exc:
                # Ya saneado en la frontera y sin la excepcion del SDK
                # encadenada: la traza no aportaria nada y podria filtrar.
                logger.warning("Fallo generando la arquitectura (%s): %s", exc.code, exc)
                yield evento({"type": "error", "code": exc.code, "detail": str(exc),
                              "missing": exc.missing})
                return
            except Exception as exc:
                logger.exception("Fallo generando la arquitectura")
                yield evento({"type": "error", "code": "internal_error",
                              "detail": sanitize(str(exc), key), "missing": []})
                return
            yield evento({"type": "done"})

        return StreamingResponse(cuerpo(), media_type="application/x-ndjson")

    # -- Especificacion de proyecto ------------------------------------

    @app.post("/api/blueprint", dependencies=[Depends(require_token)])
    def blueprint(request: BlueprintRequest) -> dict[str, Any]:
        """
        Sintetiza el PRD de un cluster.

        La sintesis es determinista y no toca disco ni red, asi que responde
        en el mismo hilo: no hay nada que esperar.
        """
        from core.intelligence.blueprint import build_blueprint

        return build_blueprint(request.cluster, request.language).to_dict()

    # -- Documento en PDF ----------------------------------------------

    @app.post("/api/document/pdf", dependencies=[Depends(require_token)])
    def document_pdf(request: DocumentRequest) -> Response:
        """
        Genera el documento de la oportunidad en PDF y devuelve sus bytes.

        Rust los guarda donde elija quien exporta: el sidecar no escribe en
        disco.
        """
        from core.documents.pdf_report import build_pdf

        pdf = build_pdf(
            request.cluster,
            request.language,
            architecture=request.architecture,
            version=SERVICE_VERSION,
        )
        return Response(content=pdf, media_type="application/pdf")

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
    from core.orchestration.graph import data_source_of

    return data_source_of(fetcher) == "reddit"


def synthetic_total() -> int:
    from core.ingestion.synthetic import total_posts

    return total_posts()


def load_dotenv(
    path: str | None, env: MutableMapping[str, str] | None = None
) -> MutableMapping[str, str]:
    """Lee un `.env` sin tocar el entorno del proceso."""
    from core.ingestion.auth import load_dotenv as _load

    return _load(path or _default_env_path(), env=env if env is not None else {})


def update_dotenv(values: dict[str, str], path: str | None = None):
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


async def _probe_reddit(auth: Any) -> tuple[bool, str, str | None]:
    """
    Comprueba las credenciales pidiendo un token real.

    Se aisla en su propia funcion para poder sustituirla en las pruebas: un
    test que salga a Reddit no es un test, es una tirada de dados.
    """
    from core.ingestion.errors import RedditAccessError

    # `get_token` traduce todo fallo (credenciales, 401, 429, 5xx, red) a
    # un RedditAccessError con codigo estable: no hay otra excepcion esperable.
    try:
        token = await auth.get_token()
        return True, f"Token obtenido correctamente ({len(token)} caracteres).", None
    except RedditAccessError as exc:
        return False, str(exc), exc.code


def _sse(payload: dict[str, Any]) -> str:
    """Serializa un evento en el formato `text/event-stream`."""
    return "data: " + json.dumps(payload, default=str) + "\n\n"


def _safe(fn, default):
    try:
        return fn()
    # Frontera de /api/health: el informe de salud no puede caerse por el
    # fallo de la pieza que esta describiendo, sea cual sea ese fallo.
    except Exception:  # noqa: BLE001
        return default


def _hit_to_camel(hit: Any) -> dict[str, Any]:
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
        "dataSource": hit.data_source,
    }


async def _persist(
    state: Mapping[str, Any],
    deps: RadarDependencies,
    postgres_dsn: str | None,
    status: str = "completed",
    data_source: str | None = None,
) -> tuple[str | None, bool, str | None]:
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

    def _write() -> tuple[str | None, bool, str | None]:
        try:
            from core.storage.postgres_store import PostgresStore, run_async

            embedder = getattr(deps.store, "embedder", None)

            async def _inner():
                async with PostgresStore(dsn=postgres_dsn) as store:
                    return await store.persist_state(
                        dict(state),
                        trigger_source="sidecar",
                        embedding_model=getattr(embedder, "name", None),
                        status=status,
                        data_source=data_source,
                    )

            summary = run_async(_inner())
            return summary.get("run_id"), True, None
        # Frontera con PostgreSQL: conexion, SQL y mapeo pueden fallar de
        # muchas formas y todas deben llegar al usuario como `persistError`.
        except Exception as exc:  # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"
            logger.error("No se pudo persistir en PostgreSQL: %s", detail)
            return None, False, detail

    return await asyncio.to_thread(_write)


def run(
    host: str = DEFAULT_HOST,
    port: int | None = None,
    token: str | None = None,
    mode: str = "reddit",
    insecure_dev: bool = False,
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
    token = token or os.environ.get(TOKEN_ENV_VAR) or None

    if not token:
        if not insecure_dev:
            logger.error(
                "Sidecar sin token: no arranca. La aplicacion lo lanza con %s; "
                "a mano, usa --insecure-dev solo para desarrollo.",
                TOKEN_ENV_VAR,
            )
            raise SystemExit(2)
        logger.warning(
            "Sidecar SIN TOKEN (--insecure-dev): cualquier proceso local puede "
            "invocarlo. Solo para desarrollo."
        )

    deps = None
    if mode == "synthetic":
        from core.ingestion.synthetic import SyntheticFetcher
        from core.storage import LanceDBStore

        from .graph import RadarDependencies

        store = LanceDBStore()
        deps = RadarDependencies(fetcher=SyntheticFetcher(), store=store)
        logger.info("Arrancando en modo DEMOSTRACION (corpus sintetico)")

    uvicorn.run(
        create_app(deps=deps, token=token, insecure_dev=insecure_dev),
        host=host,
        port=port,
        log_level="info",
    )


def main(argv: list[str] | None = None) -> int:
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
    parser.add_argument(
        "--insecure-dev",
        action="store_true",
        help="servir sin token (solo desarrollo: cualquier proceso local podra invocarlo)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(host=args.host, port=args.port, mode=args.mode, insecure_dev=args.insecure_dev)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
