"""
Estado compartido del sidecar
=============================

Lo que los routers comparten entre peticiones: persistencia, `.env`, estado
de las fuentes, vectores de la evidencia, modelos de Gemini y los escaneos en
marcha o cancelados. Viaja en un `SidecarContext` que cada router recibe al
construirse (R-D). Las dependencias del grafo antiguo, el modo demo/Reddit y
el estado del escáner de Reddit se retiraron con esa pipeline (C2).

Aquí viven también los auxiliares del `.env` que usan varios routers.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.envfile import default_env_path
from core.sources.registry import InMemorySourcesState, SourcesStateRepository

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

    persist_default: bool
    postgres_dsn: str | None
    env_path: str | None
    started_at: float
    # Escaneos en marcha y cancelaciones pendientes. Basta un set: FastAPI
    # atiende sobre un único bucle de eventos, sin concurrencia real entre
    # estas lecturas y escrituras.
    active_runs: set[str] = field(default_factory=set)
    cancelled_runs: set[str] = field(default_factory=set)
    # Tareas de fondo (escaneo multifuente): referencia fuerte hasta que terminan.
    background_tasks: set[asyncio.Task[None]] = field(default_factory=set)
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
        from core.llm.gemini import GeminiSinConfigurar, elegir_modelo

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

    def forget(self, run_id: str) -> None:
        """
        Olvida un escaneo terminado.

        Sin esto, reutilizar un identificador cancelado haría que el
        siguiente escaneo con ese id naciera muerto.
        """
        self.active_runs.discard(run_id)
        self.cancelled_runs.discard(run_id)


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
    """Estado de Gemini, SIN devolver la clave: una clave que llega al
    frontend acaba en una captura o en el inspector."""
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
