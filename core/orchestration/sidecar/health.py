"""Salud del proceso: `/api/health`."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter

from .context import SERVICE_NAME, SERVICE_VERSION, SidecarContext


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    @rutas.get("/api/health")
    def health() -> dict[str, Any]:
        """Proceso vivo, desde cuándo y si persiste. El embedder, el NLI, el
        almacén de señales y el estado del escáner de Reddit eran de la
        pipeline antigua y se retiraron con ella (C2)."""
        return {
            "status": "ok",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "uptimeSeconds": round(time.monotonic() - ctx.started_at, 3),
            "persistence": {
                "enabled": ctx.persist_default,
                "target": "postgresql" if ctx.persist_default else None,
            },
        }

    return rutas
