"""
Esquemas del dossier y del plan, y citas verificadas (E3)
=========================================================

Lo que el modelo de documentos devuelve se valida con Pydantic: sin campos de
más y con los límites fijados. Cada afirmación de mercado es un `Claim` con
ids de evidencia; `verify_claims` retira entera la que cita un id que no es de
ese veredicto. Lo técnico del plan (stack, arquitectura, modelo de datos,
pasos) no es una afirmación de mercado y no lleva cita.

Cada esquema entero es la unión de dos mitades (`...PartA`, `...PartB`): si la
respuesta se trunca, se piden por separado (E4). Se hereda B antes que A para
que las propiedades de A vayan primero: el modelo genera en ese orden.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Rúbrica fija de viabilidad (E3): estimación del modelo, no un dato medido.
VIABILITY_CRITERIA: tuple[str, ...] = (
    "complejidad_tecnica",
    "tiempo_hasta_mvp",
    "dependencias_externas",
    "coste_de_usuarios",
    "riesgo_legal",
)
ViabilityName = Literal[
    "complejidad_tecnica", "tiempo_hasta_mvp", "dependencias_externas",
    "coste_de_usuarios", "riesgo_legal",
]

#: Pasos del plan: exactamente estos (spec, Fase E).
PLAN_STEPS = 10


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Claim(_Estricto):
    """Una afirmación de mercado y la evidencia que la sostiene."""

    text: str = Field(min_length=1, max_length=700)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)


class ViabilityCriterion(_Estricto):
    criterion: ViabilityName
    score: int = Field(ge=1, le=5)
    reason: str = Field(min_length=1, max_length=400)


class StackChoice(_Estricto):
    component: str = Field(min_length=1)
    choice: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class Entity(_Estricto):
    name: str = Field(min_length=1)
    fields: list[str] = Field(min_length=1)
    purpose: str = Field(min_length=1)


class Step(_Estricto):
    number: int = Field(ge=1, le=PLAN_STEPS)
    objective: str = Field(min_length=1)
    files: list[str] = Field(min_length=1)
    commands: list[str] = Field(min_length=1)
    acceptance_tests: list[str] = Field(min_length=1)
    done_criterion: str = Field(min_length=1)


# --- Dossier -------------------------------------------------------------------

class DossierPartA(_Estricto):
    #: El problema en pocas palabras, propuesto por el modelo (E8: las palabras del
    #: grupo, sin las del tema, daban títulos como «week, morning»).
    problem_name: str = Field(min_length=1, max_length=80)
    problem: list[Claim]
    who: list[Claim]
    current_solutions: list[Claim]


class DossierPartB(_Estricto):
    why_now: list[Claim]
    risks: list[Claim]
    viability: list[ViabilityCriterion]

    @field_validator("viability")
    @classmethod
    def _cinco_criterios(cls, criterios: list[ViabilityCriterion]) -> list[ViabilityCriterion]:
        nombres = [c.criterion for c in criterios]
        if sorted(nombres) != sorted(VIABILITY_CRITERIA):
            raise ValueError(f"la viabilidad tiene que puntuar una vez cada criterio: {VIABILITY_CRITERIA}")
        return criterios


class DossierLLM(DossierPartB, DossierPartA):
    """El dossier entero tal como lo redacta el modelo."""


# --- Plan ----------------------------------------------------------------------

class PlanPartA(_Estricto):
    what_and_for_whom: list[Claim]
    mvp_in: list[Claim]
    mvp_out: list[Claim]
    stack: list[StackChoice] = Field(min_length=1)
    architecture: list[str] = Field(min_length=1)
    data_model: list[Entity] = Field(min_length=1)


class PlanPartB(_Estricto):
    steps: list[Step] = Field(min_length=PLAN_STEPS, max_length=PLAN_STEPS)
    validation: list[Claim]
    publication: list[Claim]

    @field_validator("steps")
    @classmethod
    def _numerados_en_orden(cls, pasos: list[Step]) -> list[Step]:
        if [p.number for p in pasos] != list(range(1, PLAN_STEPS + 1)):
            raise ValueError(f"los pasos van numerados del 1 al {PLAN_STEPS}, en orden")
        return pasos


class PlanLLM(PlanPartB, PlanPartA):
    """El plan entero tal como lo redacta el modelo."""


# --- Citas ---------------------------------------------------------------------

def verify_claims(claims: Iterable[Claim], valid_ids: Sequence[str] | set[str]
                  ) -> tuple[list[Claim], list[Claim]]:
    """(las que se quedan, las retiradas). Una afirmación se retira entera si
    cita algún id que no está en `valid_ids`; los ids repetidos se dejan uno."""
    validos = set(valid_ids)
    quedan: list[Claim] = []
    retiradas: list[Claim] = []
    for claim in claims:
        if claim.evidence_ids and set(claim.evidence_ids) <= validos:
            unicos = list(dict.fromkeys(claim.evidence_ids))
            quedan.append(claim.model_copy(update={"evidence_ids": unicos}))
        else:
            retiradas.append(claim)
    return quedan, retiradas
