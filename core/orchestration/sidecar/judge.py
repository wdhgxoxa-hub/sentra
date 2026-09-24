"""Top 6 del juez (con el resto de veredictos) y feed de evidencia reciente."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter

from .context import SidecarContext
from .sources import _en_camel

#: Feed de evidencia del Radar: cuántas por defecto y el máximo que se sirve.
FEED_DEFAULT = 40
FEED_MAX = 200


def _dsn(ctx: SidecarContext) -> str:
    from core.storage.postgres_store import DEFAULT_DSN, DSN_ENV_VAR

    return ctx.postgres_dsn or os.environ.get(DSN_ENV_VAR) or DEFAULT_DSN


def _leer_top(ctx: SidecarContext, run_id: str | None) -> dict[str, Any]:
    """Top de `run_id` o de la última ejecución multifuente juzgada. En un hilo:
    psycopg no funciona sobre el ProactorEventLoop de uvicorn en Windows."""
    from core.judge.store import (
        TOP_TARGET,
        current_versions,
        latest_judged_run,
        top_verdicts,
    )
    from core.storage.postgres_store import PostgresStore, run_async

    async def leer() -> dict[str, Any]:
        async with PostgresStore(dsn=_dsn(ctx)) as store:
            ejecucion = run_id or await latest_judged_run(store)
            if ejecucion is None:
                return {"run_id": None, "target": TOP_TARGET, "build_count": 0,
                        "reason": "Todavía no hay ningún escaneo juzgado.", "verdicts": [],
                        "rest": [], "current_versions": current_versions()}
            return await top_verdicts(store, ejecucion)

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
