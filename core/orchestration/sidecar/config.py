"""Configuración y credenciales de Reddit: `/api/config*` y `/api/credentials*`."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from .context import (
    SidecarContext,
    credentials_summary,
    default_env_path,
    gemini_summary,
    synthetic_total,
    update_dotenv,
)
from .schemas import CredentialsRequest, ModeRequest, ProbeResponse

logger = logging.getLogger(__name__)


async def _probe_reddit(auth: Any) -> tuple[bool, str, str | None]:
    """
    Comprueba las credenciales pidiendo un token real.

    Se aísla en su propia función para poder sustituirla en las pruebas: un
    test que salga a Reddit no es un test, es una tirada de dados.
    """
    from core.ingestion.errors import RedditAccessError

    # `get_token` traduce todo fallo (credenciales, 401, 429, 5xx, red) a
    # un RedditAccessError con código estable: no hay otra excepción esperable.
    try:
        token = await auth.get_token()
        return True, f"Token obtenido correctamente ({len(token)} caracteres).", None
    except RedditAccessError as exc:
        return False, str(exc), exc.code


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    @rutas.get("/api/config")
    def get_config() -> dict[str, Any]:
        """Lo que la vista de Configuración necesita saber."""
        return {
            "fetcherMode": ctx.mode,
            "credentials": credentials_summary(ctx),
            "envPath": str(ctx.env_path or default_env_path()),
            "syntheticPosts": synthetic_total(),
            "gemini": gemini_summary(ctx),
        }

    @rutas.post("/api/config/mode")
    def set_mode(request: ModeRequest) -> dict[str, Any]:
        """
        Cambia la fuente de datos en caliente.

        Los nodos leen `deps.fetcher` en cada llamada, así que basta con
        sustituirlo: no hace falta reconstruir el grafo ni reiniciar nada.
        """
        if request.mode == "synthetic":
            from core.ingestion.synthetic import SyntheticFetcher

            ctx.deps.fetcher = SyntheticFetcher()
        else:
            from ..pipeline import RedditFetcher

            ctx.deps.fetcher = RedditFetcher(env_path=ctx.env_path)

        ctx.mode = request.mode
        logger.info("Fuente de datos cambiada a '%s'", request.mode)
        return {"fetcherMode": request.mode}

    @rutas.post("/api/credentials")
    def save_credentials(request: CredentialsRequest) -> dict[str, Any]:
        """
        Guarda las credenciales en el `.env`.

        Se actualizan solo las claves de Reddit: el archivo suele tener más
        cosas (la conexión a PostgreSQL, rutas) y perderlas sería peor que
        no poder guardar.

        Un User-Agent que no identifica a la app y a su autor se rechaza con
        400 y código traducible, sin tocar el archivo (AUD-014).
        """
        from core.ingestion.errors import RedditUserAgentInvalid
        from core.ingestion.user_agent import validar_user_agent

        try:
            user_agent = validar_user_agent(request.userAgent)
        except RedditUserAgentInvalid as exc:
            raise HTTPException(
                status_code=400, detail={"code": exc.code, "detail": str(exc)}
            ) from None

        values = {
            "RIR_REDDIT_CLIENT_ID": request.clientId,
            "RIR_REDDIT_CLIENT_SECRET": request.clientSecret,
            "RIR_REDDIT_USER_AGENT": user_agent,
        }
        if request.username:
            values["RIR_REDDIT_USERNAME"] = request.username
        if request.password:
            values["RIR_REDDIT_PASSWORD"] = request.password

        target = update_dotenv(values, ctx.env_path)
        # El cliente construido con las credenciales anteriores ya no vale:
        # el siguiente escaneo lo rehace leyendo el `.env` recién escrito.
        invalidar = getattr(ctx.deps.fetcher, "invalidate", None)
        if callable(invalidar):
            invalidar()
        # Lo verificado era con las credenciales anteriores.
        ctx.fuente.reset()
        # Se registra que se guardó, nunca lo guardado.
        logger.info("Credenciales de Reddit actualizadas en %s", target)
        return {"saved": True, "envPath": str(target),
                "credentials": credentials_summary(ctx)}

    @rutas.post("/api/credentials/test", response_model=ProbeResponse)
    async def test_credentials() -> ProbeResponse:
        """Intenta obtener un token real con lo que hay guardado."""
        from core.ingestion.auth import load_reddit_oauth

        # La misma lectura que hace el escaneo: si aquí sale bien, el
        # escaneo usará exactamente estas credenciales.
        auth = load_reddit_oauth(ctx.env_path)
        if auth is None:
            return ProbeResponse(
                ok=False,
                detail="Faltan credenciales: guarda el Client ID y el Secret primero.",
            )

        ok, detail, code = await _probe_reddit(auth)
        if ok:
            ctx.fuente.record_success()
        else:
            ctx.fuente.record_failure(code or "reddit_auth_failed")
        return ProbeResponse(ok=ok, detail=detail)

    return rutas
