"""
Juez: ¿los problemas del grupo son el mismo? (G0)
================================================

La agrupación junta piezas por cercanía de vectores e5, y en un escaneo de un
solo tema eso junta problemas distintos (residuos de AUD2-001 y AUD2-006).
Se midió: ni la similitud e5 (cruda o centrada) ni los términos compartidos
separan en el conjunto dorado los grupos verdaderos de las mezclas. Solo un
LLM lo distingue. Por eso, una llamada por escaneo con TODOS los grupos, cada
uno con sus frases del problema verificadas (no los posts enteros): el LLM
dice si son un mismo problema concreto, el que resolvería una misma
herramienta, y por qué. El código decide con eso (gates.decide):

- medido y distinto → DESCARTAR (regla 0): una mezcla no es un nicho;
- sin comprobar (sin proveedor, con error o grupo omitido) → nunca CONSTRUIR.

coherence-v2 (escaneo de impagos): una mezcla con un problema claramente
repetido (al menos MIN_DOMINANTES frases) lo señala, y el juez lo separa como
grupo propio y lo vuelve a comprobar en otra llamada, en vez de tirar el grupo
entero. Las frases van con claves cortas por grupo (f1, f2…).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from core.llm.base import JsonGenerator, LLMError

from .gates import GateResult

logger = logging.getLogger(__name__)

COHERENCE_VERSION = "coherence-v2"
#: Por debajo, no hay problema dominante que separar (el tamaño mínimo de un grupo).
MIN_DOMINANTES = 3
MAX_OUTPUT_TOKENS = 4_000
TIMEOUT_MS = 120_000

SYSTEM_PROMPT = (
    "Eres el revisor de coherencia de un juez de nichos de mercado. Recibes grupos de frases; "
    "cada frase es la que un autor distinto escribió para contar el problema que tiene. Para "
    "cada grupo decide si TODAS las frases describen el mismo problema concreto, el que una "
    "misma herramienta resolvería, y no solo el mismo tema: «mis correos de restablecer la "
    "contraseña caen en spam» y «los de confirmación los rechaza Outlook» son el mismo problema "
    "(entregabilidad); «las alertas de DNS» y «demasiadas notificaciones en el móvil» no lo son, "
    "aunque las dos hablen de notificaciones. Devuelve same_problem y una razón breve en "
    "español (una frase). Si NO son el mismo problema, pon en dominant_ids las claves (f1, f2…) "
    "de las frases que comparten el problema concreto más repetido del grupo, solo si son al "
    "menos tres, y nómbralo en dominant_problem; si no lo hay, deja la lista vacía. No inventes "
    "grupos ni claves: responde solo con los group_id y las claves recibidas."
)


class CoherenceGroup(BaseModel):
    group_id: str
    same_problem: bool
    reason: str = Field(max_length=400)
    dominant_ids: list[str] = Field(default_factory=list)
    dominant_problem: str = Field(default="", max_length=200)


class CoherenceReport(BaseModel):
    groups: list[CoherenceGroup] = Field(default_factory=list)


Estado = Literal["mismo", "distinto", "sin_comprobar"]


@dataclass(frozen=True)
class ResultadoCoherencia:
    estado: Estado
    motivo: str
    #: Ids reales de las frases del problema dominante de una mezcla (≥ MIN_DOMINANTES).
    dominantes: tuple[str, ...] = ()
    problema_dominante: str = ""


def _resultado(respuesta: CoherenceGroup, claves: Mapping[str, str]) -> ResultadoCoherencia:
    if respuesta.same_problem:
        return ResultadoCoherencia("mismo", respuesta.reason)
    dominantes = tuple(dict.fromkeys(claves[c] for c in respuesta.dominant_ids if c in claves))
    if len(dominantes) < MIN_DOMINANTES:
        dominantes = ()
    return ResultadoCoherencia("distinto", respuesta.reason, dominantes,
                               respuesta.dominant_problem if dominantes else "")


def comprobar_coherencia(grupos: Mapping[str, Mapping[str, str]], *, provider: JsonGenerator | None,
                         model: str | None) -> dict[str, ResultadoCoherencia]:
    """{id del grupo: {id de la pieza: frase del problema}} → resultado por grupo,
    en una sola llamada."""
    if not grupos:
        return {}
    if provider is None or not model:
        return {g: ResultadoCoherencia("sin_comprobar", "sin proveedor del juez") for g in grupos}
    claves = {g: {f"f{n}": i for n, i in enumerate(frases, 1)} for g, frases in grupos.items()}
    entrada = {g: {c: grupos[g][i] for c, i in claves[g].items()} for g in grupos}
    try:
        informe = provider.generate_json(
            "¿Describe cada grupo un mismo problema?\n" + json.dumps(entrada, ensure_ascii=False),
            CoherenceReport, model=model, max_output_tokens=MAX_OUTPUT_TOKENS,
            timeout_ms=TIMEOUT_MS, system=SYSTEM_PROMPT)
    except LLMError as exc:
        logger.warning("Comprobación de coherencia no disponible: %s", exc.code)
        return {g: ResultadoCoherencia("sin_comprobar", f"coherencia no disponible: {exc.code}")
                for g in grupos}
    respuesta = {r.group_id: r for r in informe.groups if r.group_id in grupos}
    return {g: (_resultado(respuesta[g], claves[g])
                if g in respuesta else ResultadoCoherencia("sin_comprobar", "el modelo no respondió"))
            for g in grupos}


def compuerta_coherencia(resultado: ResultadoCoherencia) -> GateResult:
    """G0 con el motivo del revisor como nota; sin comprobar no se pinta como medida."""
    return GateResult("G0", resultado.estado == "mismo", 1.0 if resultado.estado == "mismo" else 0.0,
                      1.0, [], measured=resultado.estado != "sin_comprobar", note=resultado.motivo)
