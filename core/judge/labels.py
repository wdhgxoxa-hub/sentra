"""
Juez, etapa 1: etiquetado de cada ítem por el LLM
=================================================

El LLM etiqueta; no juzga. Por cada ítem devuelve is_pain (con confianza),
pain_type, intent, severity, workaround_described, wtp_signal,
competitors_mentioned y, OBLIGATORIAMENTE, el fragmento literal del texto
(`evidence_span`) que justifica cada etiqueta positiva.

Anti-alucinación: si el fragmento no aparece literalmente en el texto del
ítem, esa etiqueta se anula y queda `undetermined`. «Literal» tolera solo
diferencias de espacios, mayúsculas y forma Unicode; nunca otras palabras.
"""

from __future__ import annotations

import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

#: Intenciones posibles (F3.2).
Intent = Literal["busca_herramienta", "queja", "parche_casero", "dispuesto_a_pagar",
                 "mencion_competidor", "pregunta_neutra"]
INTENTS: tuple[str, ...] = ("busca_herramienta", "queja", "parche_casero", "dispuesto_a_pagar",
                            "mencion_competidor", "pregunta_neutra")
#: Cómo habla el ítem de un competidor.
Stance = Literal["queja", "satisfecho", "neutral"]
STANCES: tuple[str, ...] = ("queja", "satisfecho", "neutral")
#: Valor verificado de una etiqueta.
Tri = Literal["yes", "no", "undetermined"]


def _normalizar(texto: str) -> str:
    return " ".join(unicodedata.normalize("NFC", texto).casefold().split())


def span_in_text(span: str | None, text: str) -> bool:
    """¿Aparece el fragmento literalmente en el texto? Vacío = no respalda nada."""
    fragmento = _normalizar(span or "")
    return bool(fragmento) and fragmento in _normalizar(text)


class CompetitorMention(BaseModel):
    name: str
    stance: Stance
    #: ¿Lo describe el texto como gratuito? None si no lo dice.
    free: bool | None = None
    evidence_span: str = ""


class LLMItemLabel(BaseModel):
    """Lo que devuelve el LLM por ítem (sin verificar)."""

    item_id: str
    is_pain: bool
    pain_confidence: float = Field(ge=0.0, le=1.0)
    pain_type: str | None = None
    intent: Intent
    severity: Literal["baja", "media", "alta"] | None = None
    workaround_described: bool
    wtp_signal: bool
    competitors_mentioned: list[CompetitorMention] = Field(default_factory=list)
    #: Fragmento literal por etiqueta positiva: is_pain, intent, workaround_described, wtp_signal.
    evidence_spans: dict[str, str] = Field(default_factory=dict)


class LLMLabelBatch(BaseModel):
    labels: list[LLMItemLabel]
