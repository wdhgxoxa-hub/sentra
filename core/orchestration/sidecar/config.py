"""Configuración: `/api/config` (ruta del `.env` y estado de Gemini).

El cambio de fuente demo/Reddit y las credenciales de Reddit se retiraron con
la pipeline antigua (C2, D-C5): las credenciales de cada fuente viven en
`/api/sources/{id}/credentials`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .context import SidecarContext, default_env_path, gemini_summary


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    @rutas.get("/api/config")
    def get_config() -> dict[str, Any]:
        """Lo que la vista de Configuración necesita saber."""
        return {
            "envPath": str(ctx.env_path or default_env_path()),
            "gemini": gemini_summary(ctx),
        }

    return rutas
