"""
Contratos HTTP del sidecar
==========================

Peticiones y respuestas de todos los routers. Viven juntos porque son el
contrato con el puente de Rust: se revisan de una vez.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    """Búsqueda sobre la evidencia (D-C4): consulta y cuántos resultados."""

    query: str
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("La consulta no puede estar vacia")
        return value


class GeminiRequest(BaseModel):
    """Clave y modelos de Gemini. Un modelo vacío significa «automático»."""

    apiKey: str = ""
    model: str = ""
    generalModel: str = ""


class GeminiModel(BaseModel):
    id: str
    displayName: str


class GeminiModelsResponse(BaseModel):
    """Modelos que la clave puede usar y los que se usarían ahora mismo."""

    ok: bool
    code: str | None = None
    detail: str = ""
    models: list[GeminiModel] = Field(default_factory=list)
    general: str | None = None
    documents: str | None = None
    #: Cuándo se pidió la lista a Google (ISO, UTC): la interfaz lo dice (AUD2-019).
    listedAt: str | None = None


class ProbeResponse(BaseModel):
    ok: bool
    detail: str
    #: Código estable del fallo (None si fue bien): la interfaz distingue una
    #: clave rechazada de un fallo que no permitió comprobarla (D1).
    code: str | None = None


class CancelRequest(BaseModel):
    runId: str


class CancelResponse(BaseModel):
    runId: str
    # False si no habia ningun escaneo con ese id en marcha. No es un error:
    # puede ser una cancelacion anticipada, o llegar tarde.
    wasActive: bool


#: Techo de cada tope: evita un valor absurdo tecleado por error.
TOPE_MAXIMO = 1_000_000_000


class GeminiBudgetRequest(BaseModel):
    """Los topes de Configuración › Presupuesto de Gemini (llm_budget_settings)."""

    scanMaxCalls: int = Field(ge=0, le=TOPE_MAXIMO)
    scanMaxTokens: int = Field(ge=0, le=TOPE_MAXIMO)
    dailyMaxCalls: int = Field(ge=0, le=TOPE_MAXIMO)
    dailyMaxTokens: int = Field(ge=0, le=TOPE_MAXIMO)
