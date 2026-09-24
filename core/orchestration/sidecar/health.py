"""Salud del proceso: `/api/health`."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter

from core import rutas as motor

from .context import SERVICE_NAME, SERVICE_VERSION, SidecarContext


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    @rutas.get("/api/health")
    def health() -> dict[str, Any]:
        """Proceso vivo, desde cuándo, si persiste y qué código corre: la
        interfaz compara `build` con la huella con la que se compiló
        (AUD2-003). El embedder, el NLI, el almacén de señales y el estado del
        escáner de Reddit eran de la pipeline antigua y se retiraron (C2)."""
        return {
            "status": "ok",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "uptimeSeconds": round(time.monotonic() - ctx.started_at, 3),
            "persistence": {
                "enabled": ctx.persist_default,
                "target": "postgresql" if ctx.persist_default else None,
            },
            "build": motor.huella_del_motor(),
            "codeRoot": str(motor.RAIZ_CODIGO),
        }

    return rutas
