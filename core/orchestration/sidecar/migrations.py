"""
Migraciones pendientes: aviso con código, no un 500
===================================================

Si el código espera una tabla que la base aún no tiene (la rama va por
delante de las migraciones aplicadas), el motor responde 503 con el código
`migrations_pending` y la lista de lo que falta. La interfaz lo traduce.
Pasó el 2026-09-23: la base estaba en la 8 y la sección Fuentes necesitaba
la 009.
"""

from __future__ import annotations

import logging

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .context import SidecarContext

logger = logging.getLogger(__name__)

MIGRATIONS_PENDING = "migrations_pending"


def pending_migration_names(dsn: str | None) -> list[str]:
    """Migraciones del repo sin aplicar en la base (solo lectura). [] si no se sabe."""
    try:
        from core.storage.postgres_store import resolver_dsn
        from scripts.migrate import MIGRATIONS_TABLE, discover_migrations

        with psycopg.connect(resolver_dsn(dsn),
                             connect_timeout=5) as conn:
            conn.read_only = True
            aplicadas = {int(fila[0]) for fila in conn.execute(
                f"SELECT version FROM {MIGRATIONS_TABLE}")}
        return [f"{m.version:03d}_{m.name}" for m in discover_migrations()
                if m.version not in aplicadas]
    # Solo sirve para enriquecer el aviso: si no se puede saber, se dice sin lista.
    except Exception as exc:  # noqa: BLE001 - frontera con PostgreSQL
        logger.warning("No se pudo leer qué migraciones faltan: %s", type(exc).__name__)
        return []


def pending_detail(ctx: SidecarContext) -> str:
    faltan = pending_migration_names(ctx.postgres_dsn)
    if faltan:
        return f"Faltan migraciones: {', '.join(faltan)}. Aplícalas con scripts/migrate.py."
    return "La base no tiene una tabla que el motor necesita: faltan migraciones."


def install(app: FastAPI, ctx: SidecarContext) -> None:
    """Toda tabla inexistente llega a la interfaz como `migrations_pending`."""

    async def tabla_inexistente(_request: Request, exc: Exception) -> JSONResponse:
        detalle = pending_detail(ctx)
        logger.error("%s (%s)", detalle, type(exc).__name__)
        return JSONResponse(status_code=503,
                            content={"detail": {"code": MIGRATIONS_PENDING, "detail": detalle}})

    app.add_exception_handler(psycopg.errors.UndefinedTable, tabla_inexistente)
