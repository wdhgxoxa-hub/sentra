"""Palabras clave propuestas para el asistente de escaneo (Fase 2, D1):
`POST /api/scan/keywords`.

Con Gemini, una llamada del modelo general dentro de los topes del día (sin
ejecución: todavía no hay escaneo). Si no hay clave, no queda presupuesto o
Gemini falla, se proponen unas básicas sin Gemini (core/sources/palabras_clave)
y la respuesta dice por qué (`reason`), para que la pantalla lo cuente.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from core.llm.base import JsonGenerator, LLMBudgetExhausted, LLMError
from core.sources.palabras_clave import (
    PalabrasPropuestas,
    proponer_con_gemini,
    proponer_sin_gemini,
)

from .context import SidecarContext


class KeywordsRequest(BaseModel):
    topic: str = Field(max_length=200)
    languages: list[Literal["es", "en"]] = Field(min_length=1)

    @field_validator("topic")
    @classmethod
    def _con_texto(cls, valor: str) -> str:
        limpio = " ".join(valor.split())
        if not limpio:
            raise ValueError("el tema está vacío")
        return limpio


def _proveedor(ctx: SidecarContext) -> tuple[JsonGenerator, str]:
    """El modelo general con el control de Gemini del motor (tope diario)."""
    from core.llm.gemini import GeminiProvider

    clave, modelo = ctx.resolver_modelo("defecto")
    return GeminiProvider(clave, control=ctx.control()), modelo


def _proponer(ctx: SidecarContext, peticion: KeywordsRequest) -> tuple[PalabrasPropuestas, str, str | None, int]:
    """(propuesta, origen, motivo del respaldo, llamadas que salieron)."""
    try:
        proveedor, modelo = _proveedor(ctx)
        propuesta = proponer_con_gemini(proveedor, modelo, peticion.topic, peticion.languages)
    except LLMBudgetExhausted as exc:
        return proponer_sin_gemini(peticion.topic, peticion.languages), "local", exc.motivo, 0
    except LLMError as exc:
        return proponer_sin_gemini(peticion.topic, peticion.languages), "local", exc.code, 0
    return propuesta, "gemini", None, 1


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    @rutas.post("/api/scan/keywords")
    async def scan_keywords(peticion: KeywordsRequest) -> dict[str, Any]:
        propuesta, origen, motivo, llamadas = await asyncio.to_thread(_proponer, ctx, peticion)
        return {"keywords": propuesta.model_dump(), "origin": origen, "reason": motivo, "llmCalls": llamadas}

    return rutas
