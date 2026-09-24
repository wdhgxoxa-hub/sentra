"""Búsqueda sobre la evidencia multifuente (D-C4): `/api/search`.

Rama densa (vectores e5) y léxica (PostgreSQL), fusionadas con RRF en
`core.evidence.search`. La tabla LanceDB de la pipeline antigua ya no se
consulta.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter, HTTPException

from .context import SidecarContext
from .schemas import SearchRequest
from .sources import _en_camel


def _disponible(ctx: SidecarContext) -> bool:
    """Sin almacén de vectores (sidecar sin persistencia) no hay rama densa."""
    return ctx.evidence_vectors is not None


def _buscar(ctx: SidecarContext, query: str, limit: int) -> list[dict[str, Any]]:
    """Las dos ramas y la fusión. En un hilo: carga el modelo e5 la primera
    vez, y psycopg no funciona sobre el ProactorEventLoop de Windows."""
    from core.evidence.search import dense_ids, evidence_hits, fuse_rrf, lexical_ids
    from core.storage.postgres_store import (
        DEFAULT_DSN,
        DSN_ENV_VAR,
        PostgresStore,
        run_async,
    )

    assert ctx.evidence_vectors is not None
    densos = dense_ids(ctx.evidence_vectors(), query, limit)
    dsn = ctx.postgres_dsn or os.environ.get(DSN_ENV_VAR) or DEFAULT_DSN

    async def leer() -> list[dict[str, Any]]:
        async with PostgresStore(dsn=dsn) as store:
            lexicos = await lexical_ids(store, query, limit)
            return await evidence_hits(store, fuse_rrf(densos, lexicos)[:limit])

    return run_async(leer())


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    @rutas.post("/api/search")
    async def search(request: SearchRequest) -> dict[str, Any]:
        if not _disponible(ctx):
            raise HTTPException(status_code=503, detail={
                "code": "search_unavailable",
                "detail": "La búsqueda necesita la base y los vectores de la evidencia.",
            })
        hits = await asyncio.to_thread(_buscar, ctx, request.query, request.limit)
        return {"query": request.query, "hits": _en_camel(hits)}

    return rutas
