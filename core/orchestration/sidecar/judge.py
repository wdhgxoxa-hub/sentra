"""Top 6 del juez: veredictos, compuertas, corroboración y abogado del diablo."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter

from .context import SidecarContext
from .sources import _en_camel


def _leer_top(ctx: SidecarContext, run_id: str | None) -> dict[str, Any]:
    """Top de `run_id` o de la última ejecución multifuente juzgada. En un hilo:
    psycopg no funciona sobre el ProactorEventLoop de uvicorn en Windows."""
    from core.judge.store import (
        TOP_TARGET,
        current_versions,
        latest_judged_run,
        top_verdicts,
    )
    from core.storage.postgres_store import (
        DEFAULT_DSN,
        DSN_ENV_VAR,
        PostgresStore,
        run_async,
    )

    dsn = ctx.postgres_dsn or os.environ.get(DSN_ENV_VAR) or DEFAULT_DSN

    async def leer() -> dict[str, Any]:
        async with PostgresStore(dsn=dsn) as store:
            ejecucion = run_id or await latest_judged_run(store)
            if ejecucion is None:
                return {"run_id": None, "target": TOP_TARGET, "build_count": 0,
                        "reason": "Todavía no hay ningún escaneo juzgado.", "verdicts": [],
                        "current_versions": current_versions()}
            return await top_verdicts(store, ejecucion)

    return run_async(leer())


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    @rutas.get("/api/judge/top")
    async def judge_top(runId: str | None = None) -> dict[str, Any]:
        leido = await asyncio.to_thread(_leer_top, ctx, runId)
        corroboraciones = [v.get("corroboration", {}) for v in leido.get("verdicts", [])]
        respuesta: dict[str, Any] = _en_camel(leido)
        # Las claves de corroboración son ids de fuente: no se convierten.
        for veredicto, original in zip(respuesta.get("verdicts", []), corroboraciones, strict=True):
            veredicto["corroboration"] = dict(original)
        return respuesta

    return rutas
