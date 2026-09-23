"""Salud del proceso: `/api/health`."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter

from .context import SERVICE_NAME, SERVICE_VERSION, SidecarContext, safe


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    @rutas.get("/api/health")
    def health() -> dict[str, Any]:
        """
        Estado del proceso y de los modelos realmente cargados.

        Informa del motor de clasificación efectivo, no del deseado: mientras
        el NLI corra en su modo heurístico, quien consulte esto debe poder
        saberlo.
        """
        embedder = getattr(ctx.deps.store, "embedder", None)
        store_records = safe(lambda: ctx.deps.store.count_records(), -1)

        classifier = "heuristic"
        nli_available = False
        engine = ctx.deps.engine  # sin forzar su construcción
        if engine is not None:
            nli_available = getattr(engine.zeroshot_classifier, "hf_pipeline", None) is not None
            classifier = "transformers" if nli_available else "heuristic"

        return {
            "status": "ok",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "uptimeSeconds": round(time.monotonic() - ctx.started_at, 3),
            "embedder": {
                "name": getattr(embedder, "name", "desconocido"),
                "semantic": bool(getattr(embedder, "is_semantic", False)),
                "dim": int(getattr(embedder, "dim", 0) or 0),
            },
            "nli": {
                "engine": classifier,
                "available": nli_available,
                "loaded": engine is not None,
            },
            "store": {
                "path": str(getattr(ctx.deps.store, "db_path", "")),
                "records": store_records,
            },
            "persistence": {
                "enabled": ctx.persist_default,
                "target": "postgresql" if ctx.persist_default else None,
            },
            "source": ctx.estado_fuente(),
        }

    return rutas
