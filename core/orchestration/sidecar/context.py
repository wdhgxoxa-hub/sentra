"""
Estado compartido del sidecar
=============================

Lo que los routers comparten entre peticiones: las dependencias del grafo,
el modo de la fuente, lo que se sabe del acceso real a Reddit (AUD-004) y
los escaneos en marcha o cancelados. Antes eran variables capturadas por los
closures de `create_app`; ahora viajan en un `SidecarContext` que cada router
recibe al construirse (R-D).

Aquí viven también los auxiliares del `.env` que usan varios routers.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.envfile import default_env_path
from core.sources.registry import InMemorySourcesState, SourcesStateRepository

from ..graph import RadarDependencies, data_source_of
from ..pipeline import RadarPipeline
from ..source_status import SourceTracker

if TYPE_CHECKING:
    from core.evidence.vectors import EvidenceVectorStore
    from core.llm.base import ModelInfo
    from core.llm.gemini import UsoDeModelo

#: Cuánto se reutiliza la lista de modelos de una clave antes de volver a
#: pedirla: cada petición a models.list es una llamada real a la API.
MODELOS_TTL_S = 600.0

SERVICE_NAME = "reddit-intelligence-radar-sidecar"
SERVICE_VERSION = "0.1.0"



@dataclass
class SidecarContext:
    """Estado de una aplicación del sidecar, compartido por sus routers."""

    deps: RadarDependencies
    pipeline: RadarPipeline
    persist_default: bool
    postgres_dsn: str | None
    env_path: str | None
    started_at: float
    # "reddit" o "synthetic". Se cambia en caliente desde la configuración.
    mode: str
    # Lo que ha pasado de verdad contra Reddit (AUD-004). Alimenta el
    # indicador de la fuente: solo un 200 real lo pone en verde.
    fuente: SourceTracker = field(default_factory=SourceTracker)
    # Escaneos en marcha y cancelaciones pendientes. Basta un set: FastAPI
    # atiende sobre un único bucle de eventos, sin concurrencia real entre
    # estas lecturas y escrituras.
    active_runs: set[str] = field(default_factory=set)
    cancelled_runs: set[str] = field(default_factory=set)
    # Estado verificado de cada fuente (F2.4): PostgreSQL en producción.
    sources_state: SourcesStateRepository = field(default_factory=InMemorySourcesState)
    # Vectores e5 de la evidencia (dedup semántica y clustering). Perezoso:
    # cargar el modelo tarda; None = solo deduplicación por huella.
    evidence_vectors: Callable[[], EvidenceVectorStore] | None = None
    # Modelos de Gemini por huella de la clave (nunca la clave): (hora, lista).
    modelos_gemini: dict[str, tuple[float, list[ModelInfo]]] = field(default_factory=dict)

    def listar_modelos(self, key: str, *, refrescar: bool = False) -> list[ModelInfo]:
        """Modelos que la clave puede usar, reutilizando la lista un rato."""
        from core.llm.gemini import GeminiProvider

        huella = hashlib.sha256(key.encode()).hexdigest()
        guardada = self.modelos_gemini.get(huella)
        if guardada and not refrescar and time.monotonic() - guardada[0] < MODELOS_TTL_S:
            return guardada[1]
        modelos = GeminiProvider(key).list_models()
        self.modelos_gemini[huella] = (time.monotonic(), modelos)
        return modelos

    def resolver_modelo(self, uso: UsoDeModelo) -> tuple[str, str]:
        """Clave y modelo de Gemini para un uso («defecto» o «documentos»).

        Lanza GeminiSinConfigurar sin clave, LLMModelUnavailable si el
        guardado desapareció o no hay candidato, y GeminiError si la API
        falla al listar.
        """
        from core.intelligence.gemini_architect import GeminiSinConfigurar
        from core.llm.gemini import elegir_modelo

        credenciales = gemini_credenciales(self)
        if not credenciales.key:
            raise GeminiSinConfigurar(
                "No hay clave de Gemini guardada. Se configura en Ajustes."
            )
        guardado = (
            credenciales.documents_model if uso == "documentos" else credenciales.general_model
        )
        modelo = elegir_modelo(self.listar_modelos(credenciales.key), uso, guardado=guardado)
        return credenciales.key, modelo.id

    def estado_fuente(self) -> dict[str, Any]:
        from core.ingestion.auth import load_reddit_oauth

        return self.fuente.snapshot(self.mode, load_reddit_oauth(self.env_path) is not None)

    def registrar_escaneo(self, es_reddit: bool, final_state: Mapping[str, Any]) -> None:
        """Anota el desenlace de un escaneo si lo sirvió Reddit.

        Solo un escaneo en modo Reddit que llegó a descargar sin fallo es un
        200 real de la API OAuth: el corpus fabricado nunca verifica nada.
        """
        if not es_reddit:
            return
        failure = final_state.get("failure")
        if failure:
            self.fuente.record_failure(str(failure["code"]))
        elif int(final_state.get("cycle", 0) or 0) >= 1:
            self.fuente.record_success()

    def forget(self, run_id: str) -> None:
        """
        Olvida un escaneo terminado.

        Sin esto, reutilizar un identificador cancelado haría que el
        siguiente escaneo con ese id naciera muerto.
        """
        self.active_runs.discard(run_id)
        self.cancelled_runs.discard(run_id)


# --- Fuente de datos ---------------------------------------------------------

def is_reddit_fetcher(fetcher: Any) -> bool:
    return data_source_of(fetcher) == "reddit"


def synthetic_total() -> int:
    from core.ingestion.synthetic import total_posts

    return total_posts()


def safe[T](fn: Callable[[], T], default: T) -> T:
    try:
        return fn()
    # Frontera de /api/health: el informe de salud no puede caerse por el
    # fallo de la pieza que está describiendo, sea cual sea ese fallo.
    except Exception:  # noqa: BLE001 - el informe de salud no puede caerse
        return default


# --- .env ------------------------------------------------------------------------

def load_dotenv(
    path: str | None, env: MutableMapping[str, str] | None = None
) -> MutableMapping[str, str]:
    """Lee un `.env` sin tocar el entorno del proceso."""
    from core.ingestion.auth import load_dotenv as _load

    return _load(path or default_env_path(), env=env if env is not None else {})


@dataclass(frozen=True)
class GeminiCredenciales:
    """Lo guardado en el `.env`. Un modelo None significa «automático»."""

    key: str
    documents_model: str | None
    general_model: str | None


def gemini_credenciales(ctx: SidecarContext) -> GeminiCredenciales:
    """Clave y modelos de Gemini guardados en el `.env`.

    RIR_GEMINI_MODEL es el de documentos (el plan de arquitectura, su uso
    de siempre); RIR_GEMINI_GENERAL_MODEL, el de traducción y etiquetado.
    """
    values = load_dotenv(ctx.env_path, env={})
    return GeminiCredenciales(
        key=(values.get("RIR_GEMINI_API_KEY") or "").strip(),
        documents_model=(values.get("RIR_GEMINI_MODEL") or "").strip() or None,
        general_model=(values.get("RIR_GEMINI_GENERAL_MODEL") or "").strip() or None,
    )


def gemini_summary(ctx: SidecarContext) -> dict[str, Any]:
    """Estado del motor de arquitectura, SIN devolver la clave.

    Vale lo mismo que para el secreto de Reddit: una clave que llega al
    frontend acaba en una captura o en el inspector.
    """
    credenciales = gemini_credenciales(ctx)
    key = credenciales.key
    masked = ""
    if key:
        masked = key[:6] + "…" + key[-4:] if len(key) > 12 else "…"
    return {
        "configured": bool(key),
        "keyMasked": masked,
        "model": credenciales.documents_model,
        "generalModel": credenciales.general_model,
    }


def credentials_summary(ctx: SidecarContext) -> dict[str, Any]:
    """
    Estado de las credenciales SIN devolver el secreto.

    Un secreto que viaja al frontend acaba en el log de alguien, en una
    captura de pantalla o en el inspector del navegador.
    """
    values = load_dotenv(ctx.env_path, env={})
    client_id = (values.get("RIR_REDDIT_CLIENT_ID") or "").strip()
    secret = (values.get("RIR_REDDIT_CLIENT_SECRET") or "").strip()

    masked = ""
    if client_id:
        masked = client_id[:4] + "…" + client_id[-2:] if len(client_id) > 6 else "…"

    return {
        "configured": bool(client_id and secret),
        "clientIdMasked": masked,
        "userAgent": (values.get("RIR_REDDIT_USER_AGENT") or "").strip(),
        "hasUser": bool((values.get("RIR_REDDIT_USERNAME") or "").strip()),
    }
