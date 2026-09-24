"""
Servidor Sidecar (resolución de la deuda D14)
=============================================

Expone por HTTP local lo que el proceso Rust no resuelve por su cuenta: las
fuentes y su escaneo, el juez, la búsqueda sobre la evidencia y Gemini.

Las rutas viven en routers por responsabilidad (`core/orchestration/sidecar/`,
R-D): salud, configuración, Gemini, búsqueda, fuentes, escaneo multifuente y
juez. Este módulo los monta, con el token por delante de todos. La pipeline
antigua de Reddit (escaneo por subreddit, documentos por cluster) se retiró
en C2.

Dos decisiones de seguridad
---------------------------
1. **Solo loopback.** El servidor escucha en 127.0.0.1. Un sidecar de
   escritorio no tiene ningún motivo para ser alcanzable desde la red.
2. **Token obligatorio (D-B).** Incluso en loopback, cualquier proceso del
   equipo podría lanzar un escaneo, que consume cuota de las fuentes, o leer
   la configuración. La aplicación de escritorio genera un token aleatorio
   en cada arranque y lo pasa en `RIR_SIDECAR_TOKEN`; cada petición lo trae
   en `Authorization: Bearer`, y se compara en tiempo constante. Sin token
   el sidecar no arranca, salvo con `--insecure-dev` explícito.

Ejecución (la aplicación lo lanza sola; a mano, solo para desarrollo):

    RIR_SIDECAR_TOKEN=<64 hex> python -m core.orchestration.sidecar_server
    python -m core.orchestration.sidecar_server --insecure-dev --port 9000
"""

from __future__ import annotations

import functools
import hmac
import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from core.envfile import EnvValueInvalid
from core.rutas import ruta_cache_modelos_gemini
from core.sources.registry import (
    InMemorySourcesState,
    PostgresSourcesState,
    SourcesStateRepository,
)

from .sidecar import (
    config,
    documents,
    gemini,
    health,
    judge,
    migrations,
    multiscan,
    search,
    sources,
)
from .sidecar.context import SERVICE_NAME, SERVICE_VERSION, SidecarContext

if TYPE_CHECKING:
    from core.evidence.vectors import EvidenceVectorStore

logger = logging.getLogger(__name__)

# Loopback a propósito: ver la nota de seguridad de arriba.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

PORT_ENV_VAR = "RIR_SIDECAR_PORT"
TOKEN_ENV_VAR = "RIR_SIDECAR_TOKEN"

#: Longitud mínima del token. El de la aplicación son 64 caracteres hex
#: (32 bytes aleatorios); uno corto se podría adivinar.
MIN_TOKEN_LENGTH = 32

#: Routers montados, en este orden.
ROUTERS = (health, config, gemini, search, sources, multiscan, judge, documents)


class SidecarSinToken(RuntimeError):
    """El sidecar no puede servir sin token salvo con `--insecure-dev`."""


def _estado_de_fuentes(persist: bool, postgres_dsn: str | None) -> SourcesStateRepository:
    """sources_state en PostgreSQL si se persiste; en memoria si no (tests, demo sin base)."""
    if not persist:
        return InMemorySourcesState()
    from core.storage.postgres_store import resolver_dsn

    return PostgresSourcesState(resolver_dsn(postgres_dsn))


def _vectores_de_evidencia() -> Callable[[], EvidenceVectorStore]:
    """El almacén e5 se abre la primera vez que un escaneo lo pide, y una sola vez."""

    @functools.cache
    def abrir() -> EvidenceVectorStore:
        from core.evidence.vectors import EvidenceVectorStore

        return EvidenceVectorStore()

    return abrir


def create_app(
    token: str | None = None,
    persist_default: bool = True,
    postgres_dsn: str | None = None,
    env_path: str | None = None,
    insecure_dev: bool = False,
    cache_modelos: Path | None = None,
) -> FastAPI:
    """
    Construye la aplicación.

    Args:
        token: cada petición debe traerlo en `Authorization: Bearer`.
            Obligatorio, de al menos MIN_TOKEN_LENGTH caracteres.
        insecure_dev: permite servir sin token (desarrollo y tests que no
            prueban la seguridad). Hay que pedirlo explícitamente.
        persist_default: si los escaneos vuelcan a PostgreSQL por defecto (y
            con ello si hay juez, búsqueda y vectores de la evidencia).
        postgres_dsn: cadena de conexión para esa persistencia.
        env_path: archivo de configuración que gestiona la vista de ajustes.
        cache_modelos: fichero donde la lista de modelos de Gemini sobrevive
            entre arranques (AUD2-019); None = solo en memoria.
    """
    if token is not None and len(token) < MIN_TOKEN_LENGTH:
        raise SidecarSinToken(f"El token debe tener al menos {MIN_TOKEN_LENGTH} caracteres.")
    if token is None and not insecure_dev:
        raise SidecarSinToken(
            f"Falta {TOKEN_ENV_VAR}. Solo con --insecure-dev puede servirse sin token."
        )

    ctx = SidecarContext(
        persist_default=persist_default,
        postgres_dsn=postgres_dsn,
        env_path=env_path,
        started_at=time.monotonic(),
        sources_state=_estado_de_fuentes(persist_default, postgres_dsn),
        evidence_vectors=_vectores_de_evidencia() if persist_default else None,
        cache_modelos=cache_modelos,
    )

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

    app = FastAPI(
        title=SERVICE_NAME,
        version=SERVICE_VERSION,
        docs_url=None,       # sin documentación interactiva: no es una API pública
        redoc_url=None,
        openapi_url=None,
    )
    migrations.install(app, ctx)

    @app.exception_handler(EnvValueInvalid)
    async def env_invalido(_request: Request, exc: EnvValueInvalid) -> JSONResponse:
        """AUD-036: lo que no cabe en el `.env` tal cual se rechaza con código,
        en cualquier ruta que lo escriba, y el archivo no se toca."""
        return JSONResponse(status_code=400, content={"detail": {"code": exc.code, "detail": str(exc)}})
    for modulo in ROUTERS:
        # Se copian las rutas en lugar de `include_router`: desde FastAPI
        # 0.141 un router incluido queda como un nodo perezoso y `app.routes`
        # deja de listar las rutas, que es la superficie que se comprueba.
        for ruta in modulo.router(ctx).routes:
            assert isinstance(ruta, APIRoute), ruta
            assert ruta.methods, ruta  # APIRoute siempre los rellena ({"GET"} por defecto)
            app.add_api_route(
                ruta.path,
                ruta.endpoint,
                methods=sorted(ruta.methods),
                response_model=ruta.response_model,
                name=ruta.name,
                dependencies=[*ruta.dependencies, Depends(require_token)],
            )
    return app


def vigilar_padre(entrada: BinaryIO | None, salir: Callable[[int], object]) -> threading.Thread:
    """Termina el proceso cuando se cierra `entrada`, la tubería de la aplicación.

    La aplicación lanza el motor con su entrada estándar conectada a una
    tubería que nunca escribe. Si la aplicación muere, de la forma que sea, el
    sistema cierra su extremo y la lectura devuelve fin de archivo: el motor
    sale en lugar de quedarse huérfano con el puerto y un token que nadie
    conoce. Sin entrada, la aplicación ya no está. `salir` es `os._exit` en
    producción: sale aunque uvicorn tenga hilos o peticiones en curso.
    """

    def esperar() -> None:
        if entrada is not None:
            while entrada.read(4096):
                pass
        logger.info("La aplicación ya no está (entrada cerrada): el motor se detiene")
        salir(0)

    hilo = threading.Thread(target=esperar, name="vigilar-padre", daemon=True)
    hilo.start()
    return hilo


def run(
    host: str = DEFAULT_HOST,
    port: int | None = None,
    token: str | None = None,
    insecure_dev: bool = False,
) -> None:
    """Arranca el servidor con uvicorn."""
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

    uvicorn.run(
        create_app(token=token, insecure_dev=insecure_dev, cache_modelos=ruta_cache_modelos_gemini()),
        host=host,
        port=port,
        log_level="info",
    )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Sidecar de SENTRA")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument(
        "--insecure-dev",
        action="store_true",
        help="servir sin token (solo desarrollo: cualquier proceso local podra invocarlo)",
    )
    parser.add_argument(
        "--exit-with-parent",
        action="store_true",
        help="terminar cuando se cierre la entrada estandar (la aplicacion la mantiene abierta)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.exit_with_parent:
        vigilar_padre(sys.stdin.buffer if sys.stdin is not None else None, os._exit)
    run(host=args.host, port=args.port, insecure_dev=args.insecure_dev)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
