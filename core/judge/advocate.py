"""
Juez, etapa 5: abogado del diablo (solo puede bajar)
====================================================

Para cada candidato a CONSTRUIR, el LLM recibe la evidencia y devuelve en
JSON los argumentos más fuertes EN CONTRA, cada uno citando ids de
evidencia. El paso es determinista sobre esa salida:

- Un argumento que cita ids ajenos al grupo se descarta (anti-alucinación).
- Solo un argumento válido de gravedad en DOWNGRADE_SEVERITIES baja el
  veredicto a INVESTIGAR MÁS, con motivo registrado. El resto se muestra.
- Nunca sube: fuera de CONSTRUIR no se ejecuta.
- Si no puede ejecutarse (sin proveedor o con error), el CONSTRUIR sin
  revisar baja a INVESTIGAR MÁS: un falso CONSTRUIR es el peor error.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from core.evidence.model import EvidenceItem
from core.llm.base import LLMError, LLMProvider

from .gates import ClusterJudgement, Verdict

logger = logging.getLogger(__name__)

DOWNGRADE_SEVERITIES = frozenset({"bloqueante"})
MAX_OUTPUT_TOKENS = 4_000
TIMEOUT_MS = 120_000

SYSTEM_PROMPT = (
    "Eres el abogado del diablo de un juez de nichos de mercado. Te dan la evidencia de un "
    "nicho candidato a construir. Devuelve los argumentos más fuertes EN CONTRA de construirlo, "
    "cada uno citando los ids de evidencia que lo sostienen. Gravedad: 'bloqueante' si por sí "
    "solo desaconseja construir, 'importante' o 'menor' si no. No inventes ids."
)


class AdvocateArgument(BaseModel):
    claim: str
    evidence_ids: list[str] = Field(min_length=1)
    severity: Literal["bloqueante", "importante", "menor"]


class AdvocateReport(BaseModel):
    arguments: list[AdvocateArgument] = Field(default_factory=list)


@dataclass
class AdvocateOutcome:
    verdict_before: Verdict
    verdict_after: Verdict
    downgraded: bool
    #: Por qué bajó (o not_applicable / advocate_unavailable); None si revisó y no bajó.
    reason: str | None
    arguments: list[AdvocateArgument] = field(default_factory=list)
    discarded: list[AdvocateArgument] = field(default_factory=list)


def apply_advocate(juicio: ClusterJudgement, informe: AdvocateReport,
                   member_ids: Iterable[str]) -> AdvocateOutcome:
    miembros = set(member_ids)
    validos = [a for a in informe.arguments if set(a.evidence_ids) <= miembros]
    descartados = [a for a in informe.arguments if not set(a.evidence_ids) <= miembros]
    if juicio.verdict != "CONSTRUIR":
        return AdvocateOutcome(juicio.verdict, juicio.verdict, False, "not_applicable",
                               validos, descartados)
    bloqueantes = [a for a in validos if a.severity in DOWNGRADE_SEVERITIES]
    if bloqueantes:
        motivo = "argumento bloqueante: " + bloqueantes[0].claim
        return AdvocateOutcome("CONSTRUIR", "INVESTIGAR MÁS", True, motivo, validos, descartados)
    return AdvocateOutcome("CONSTRUIR", "CONSTRUIR", False, None, validos, descartados)


def _prompt(items: Sequence[EvidenceItem]) -> str:
    evidencia = [{"id": i.id, "source": i.source, "text": i.text[:1500]} for i in items]
    return ("Argumentos en contra de construir para este nicho. Evidencia:\n"
            + json.dumps(evidencia, ensure_ascii=False))


def run_advocate(juicio: ClusterJudgement, items: Sequence[EvidenceItem], *,
                 provider: LLMProvider | None, model: str | None) -> AdvocateOutcome:
    if juicio.verdict != "CONSTRUIR":
        return AdvocateOutcome(juicio.verdict, juicio.verdict, False, "not_applicable")
    if provider is None or not model:
        return AdvocateOutcome("CONSTRUIR", "INVESTIGAR MÁS", True, "advocate_unavailable")
    try:
        informe = provider.generate_json(_prompt(items), AdvocateReport, model=model,
                                         max_output_tokens=MAX_OUTPUT_TOKENS,
                                         timeout_ms=TIMEOUT_MS, system=SYSTEM_PROMPT)
    except LLMError as exc:
        logger.warning("Abogado del diablo no disponible: %s", exc.code)
        return AdvocateOutcome("CONSTRUIR", "INVESTIGAR MÁS", True,
                               f"advocate_unavailable:{exc.code}")
    return apply_advocate(juicio, informe, (i.id for i in items))
