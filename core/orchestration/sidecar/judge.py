"""Top 6 del juez (con el resto de veredictos) y feed de evidencia reciente."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter

from core.privacidad import ocultar_identificadores

from .context import SidecarContext
from .sources import _en_camel

#: Feed de evidencia del Radar: cuántas por defecto y el máximo que se sirve.
FEED_DEFAULT = 40
FEED_MAX = 200


def _dsn(ctx: SidecarContext) -> str:
    from core.storage.postgres_store import resolver_dsn

    return resolver_dsn(ctx.postgres_dsn)


def _leer_top(ctx: SidecarContext, run_id: str | None) -> dict[str, Any]:
    """Top de `run_id` o el del Radar (core/judge/store.py, leer_radar). En un
    hilo: psycopg no funciona sobre el ProactorEventLoop de uvicorn en Windows."""
    from core.judge.store import leer_radar
    from core.storage.postgres_store import PostgresStore, run_async

    async def leer() -> dict[str, Any]:
        async with PostgresStore(dsn=_dsn(ctx)) as store:
            return await leer_radar(store, run_id)

    return run_async(leer())


def _leer_feed(ctx: SidecarContext, limit: int) -> list[dict[str, Any]]:
    """Evidencia más reciente, en un hilo por la misma razón que el Top."""
    from core.judge.store import recent_evidence
    from core.storage.postgres_store import PostgresStore, run_async

    async def leer() -> list[dict[str, Any]]:
        async with PostgresStore(dsn=_dsn(ctx)) as store:
            return await recent_evidence(store, limit)

    return run_async(leer())


def _veredictos_en_camel(originales: list[dict[str, Any]]) -> list[dict[str, Any]]:
    convertidos: list[dict[str, Any]] = _en_camel(originales)
    # Las claves de corroboración son ids de fuente: no se convierten.
    for veredicto, original in zip(convertidos, originales, strict=True):
        veredicto["corroboration"] = dict(original.get("corroboration", {}))
        # R9 (Fase 3): la clave interna del grupo se forma con ids de piezas y
        # el de Bluesky lleva el DID del autor; la interfaz no la necesita.
        veredicto.pop("clusterKey", None)
        for pieza in veredicto.get("evidence") or []:
            pieza["excerpt"] = ocultar_identificadores(str(pieza.get("excerpt") or ""))
    return convertidos


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    @rutas.get("/api/judge/top")
    async def judge_top(runId: str | None = None) -> dict[str, Any]:
        leido = await asyncio.to_thread(_leer_top, ctx, runId)
        respuesta: dict[str, Any] = _en_camel(leido)
        respuesta["verdicts"] = _veredictos_en_camel(leido.get("verdicts", []))
        respuesta["rest"] = _veredictos_en_camel(leido.get("rest", []))
        return respuesta

    @rutas.get("/api/evidence/recent")
    async def evidence_recent(limit: int = FEED_DEFAULT) -> dict[str, Any]:
        tope = max(1, min(limit, FEED_MAX))
        items = await asyncio.to_thread(_leer_feed, ctx, tope)
        return {"items": _en_camel(items)}

    return rutas
