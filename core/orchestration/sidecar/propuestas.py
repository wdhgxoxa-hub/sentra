"""Propuestas de escaneo de Claude Desktop (core/propuestas.py): la ventana las
lista y las descarta; lanzarlas va por el escaneo de siempre (multiscan.py)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException

from .context import SidecarContext


def _hay_base(ctx: SidecarContext) -> bool:
    """Sin persistencia (tests, modo sin base) no hay propuestas."""
    return ctx.persist_default


def _dsn(ctx: SidecarContext) -> str:
    from core.storage.postgres_store import resolver_dsn

    return resolver_dsn(ctx.postgres_dsn)


def _para_la_interfaz(fila: dict[str, Any]) -> dict[str, Any]:
    """En camelCase, como el resto del motor. Del perfil solo sus claves: dentro
    van palabras del tema (`keyword_languages`) que no se tocan."""
    from core.orchestration.sidecar.sources import _camel

    convertida = {_camel(k): v for k, v in fila.items()}
    if isinstance(convertida.get("profile"), dict):
        convertida["profile"] = {_camel(k): v for k, v in convertida["profile"].items()}
    return convertida


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    @rutas.get("/api/scan-requests")
    async def scan_requests() -> dict[str, Any]:
        from core import propuestas

        if not _hay_base(ctx):
            return {"requests": []}
        filas = await asyncio.to_thread(propuestas.pendientes, _dsn(ctx))
        return {"requests": [_para_la_interfaz(f) for f in filas]}

    @rutas.post("/api/scan-requests/{request_id}/discard")
    async def discard(request_id: str) -> dict[str, Any]:
        from core import propuestas

        if not _hay_base(ctx) or not await asyncio.to_thread(propuestas.descartar, _dsn(ctx), request_id):
            raise HTTPException(status_code=404, detail={"code": "scan_request_not_pending",
                                                         "detail": "Esa propuesta ya no está pendiente."})
        return {"discarded": True}

    return rutas
