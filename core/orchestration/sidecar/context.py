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
import json
import logging
import time
from collections.abc import Callable, MutableMapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.envfile import default_env_path
from core.llm.control import ControlDeGemini, RegistroDeUso, RegistroEnMemoria
from core.sources.registry import InMemorySourcesState, SourcesStateRepository

if TYPE_CHECKING:
    from core.documents.model import DocumentModel
    from core.evidence.vectors import EvidenceVectorStore
    from core.llm.base import ModelInfo
    from core.llm.gemini import UsoDeModelo

#: Cuánto se reutiliza la lista de modelos de una clave antes de volver a
#: pedirla: cada petición a models.list es una llamada real a la API. Se
#: guarda en disco (AUD2-019): abrir Configuración tras un arranque no la
#: vuelve a pedir. «Probar» sí pregunta siempre.
MODELOS_TTL_S = 24 * 3600.0

logger = logging.getLogger(__name__)

SERVICE_NAME = "sentra-sidecar"
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
    # Dossier y plan ya generados, por (veredicto, documento, idioma, modelo,
    # forzado): exportar el otro formato no vuelve a llamar al modelo (Fase E).
    documentos: dict[tuple[str, str, str, str, bool], DocumentModel] = field(default_factory=dict)
    # Modelos de Gemini por huella de la clave (nunca la clave): (hora epoch, lista).
    modelos_gemini: dict[str, tuple[float, list[ModelInfo]]] = field(default_factory=dict)
    # Fichero donde sobrevive esa lista entre arranques; None = solo en memoria.
    cache_modelos: Path | None = None
    # Dónde queda cada intento de llamada a Gemini (llm_usage, migración 017):
    # PostgreSQL con persistencia; en memoria sin ella (tests, demo sin base),
    # como sources_state. Nadie resuelve aquí el DSN por su cuenta.
    registro_de_uso: RegistroDeUso = field(default_factory=RegistroEnMemoria)

    def control(self, run_id: str | None = None) -> ControlDeGemini:
        """El punto de control de Gemini de este motor, cargado a `run_id`."""
        return ControlDeGemini(self.registro_de_uso, run_id=run_id)

    def listar_modelos(self, key: str, *, refrescar: bool = False) -> list[ModelInfo]:
        """Modelos que la clave puede usar, reutilizando la lista un día."""
        return self.listar_modelos_con_hora(key, refrescar=refrescar)[1]

    def listar_modelos_con_hora(self, key: str, *, refrescar: bool = False) -> tuple[float, list[ModelInfo]]:
        """(cuándo se pidió a Google, en epoch; lista)."""
        from core.llm.gemini import GeminiProvider

        huella = hashlib.sha256(key.encode()).hexdigest()[:32]
        if not refrescar:
            guardada = self.modelos_gemini.get(huella) or self._leer_cache_modelos(huella)
            if guardada and time.time() - guardada[0] < MODELOS_TTL_S:
                self.modelos_gemini[huella] = guardada
                return guardada
        # El listado queda en llm_usage (listado_modelos) pero no cuenta para los topes.
        self.modelos_gemini[huella] = (time.time(), GeminiProvider(key, control=self.control()).list_models())
        self._escribir_cache_modelos()
        return self.modelos_gemini[huella]

    def olvidar_modelos(self) -> None:
        """La lista era de otra clave (o de la misma antes de guardarla otra vez)."""
        self.modelos_gemini.clear()
        if self.cache_modelos is not None:
            self.cache_modelos.unlink(missing_ok=True)

    def _leer_cache_modelos(self, huella: str) -> tuple[float, list[ModelInfo]] | None:
        from core.llm.base import ModelInfo

        if self.cache_modelos is None or not self.cache_modelos.is_file():
            return None
        try:
            entrada = json.loads(self.cache_modelos.read_text("utf-8")).get(huella)
            if not entrada:
                return None
            return float(entrada["listed_at"]), [ModelInfo(**m) for m in entrada["models"]]
        except (OSError, ValueError, TypeError, KeyError) as exc:
            logger.warning("Caché de modelos de Gemini ilegible; se volverá a pedir: %s", type(exc).__name__)
            return None

    def _escribir_cache_modelos(self) -> None:
        if self.cache_modelos is None:
            return
        datos = {huella: {"listed_at": hora, "models": [asdict(m) for m in modelos]}
                 for huella, (hora, modelos) in self.modelos_gemini.items()}
        try:
            self.cache_modelos.parent.mkdir(parents=True, exist_ok=True)
            temporal = self.cache_modelos.with_suffix(".tmp")
            temporal.write_text(json.dumps(datos), "utf-8")
            temporal.replace(self.cache_modelos)
        except OSError as exc:
            logger.warning("No se pudo guardar la caché de modelos de Gemini: %s", type(exc).__name__)

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
        # AUD-062: solo los 4 últimos, lo justo para reconocer cuál es.
        masked = "…" + key[-4:] if len(key) > 12 else "…"
    return {
        "configured": bool(key),
        "keyMasked": masked,
        "model": credenciales.documents_model,
        "generalModel": credenciales.general_model,
    }
