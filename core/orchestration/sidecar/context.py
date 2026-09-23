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

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from ..graph import RadarDependencies, data_source_of
from ..pipeline import RadarPipeline
from ..source_status import SourceTracker

SERVICE_NAME = "reddit-intelligence-radar-sidecar"
SERVICE_VERSION = "0.1.0"

T = TypeVar("T")


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


def safe(fn: Callable[[], T], default: T) -> T:
    try:
        return fn()
    # Frontera de /api/health: el informe de salud no puede caerse por el
    # fallo de la pieza que está describiendo, sea cual sea ese fallo.
    except Exception:  # noqa: BLE001
        return default


# --- .env ------------------------------------------------------------------------

def default_env_path() -> str:
    """Ruta del `.env` del proyecto."""
    return str(Path(__file__).resolve().parents[3] / ".env")


def load_dotenv(
    path: str | None, env: MutableMapping[str, str] | None = None
) -> MutableMapping[str, str]:
    """Lee un `.env` sin tocar el entorno del proceso."""
    from core.ingestion.auth import load_dotenv as _load

    return _load(path or default_env_path(), env=env if env is not None else {})


def update_dotenv(values: dict[str, str], path: str | None = None) -> Path:
    """
    Escribe o actualiza claves en un `.env`, preservando el resto.

    Se reescribe el archivo entero en lugar de anexar: anexar dejaría
    duplicados y la última línea ganaría en silencio.
    """
    target = Path(path or default_env_path())
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


def gemini_credenciales(ctx: SidecarContext) -> tuple[str, str]:
    """Clave y modelo de Gemini guardados en el `.env`."""
    from core.intelligence.gemini_architect import MODELO_POR_DEFECTO

    values = load_dotenv(ctx.env_path, env={})
    key = (values.get("RIR_GEMINI_API_KEY") or "").strip()
    model = (values.get("RIR_GEMINI_MODEL") or "").strip() or MODELO_POR_DEFECTO
    return key, model


def gemini_summary(ctx: SidecarContext) -> dict[str, Any]:
    """Estado del motor de arquitectura, SIN devolver la clave.

    Vale lo mismo que para el secreto de Reddit: una clave que llega al
    frontend acaba en una captura o en el inspector.
    """
    key, model = gemini_credenciales(ctx)
    masked = ""
    if key:
        masked = key[:6] + "…" + key[-4:] if len(key) > 12 else "…"
    return {"configured": bool(key), "keyMasked": masked, "model": model}


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
