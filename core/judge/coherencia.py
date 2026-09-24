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

coherence-v3 (tras E8): un grupo que es un mismo problema sale nombrado en es y
en (el nombre que comparten el Radar y el dossier), y cada resultado medido se
guarda por grupo (hash de sus pares id/frase) y revisor (versión y modelo): el
mismo grupo da el mismo resultado sin volver a preguntar. La temperatura se
deja por defecto (Google la desaconseja por debajo de 1,0 en Gemini 3).
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from core.llm.base import JsonGenerator, LLMError

from .gates import GateResult

logger = logging.getLogger(__name__)

COHERENCE_VERSION = "coherence-v3"
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
    "menos tres, y nómbralo en dominant_problem; si no lo hay, deja la lista vacía. Si SÍ son el "
    "mismo problema, nómbralo en problem_name_es (español, con tildes) y en problem_name_en "
    "(inglés): pocas palabras (máximo ocho), desde quien lo sufre y sin nombres de empresas. No "
    "inventes grupos ni claves: responde solo con los group_id y las claves recibidas."
)


class CoherenceGroup(BaseModel):
    group_id: str
    same_problem: bool
    reason: str = Field(max_length=400)
    dominant_ids: list[str] = Field(default_factory=list)
    dominant_problem: str = Field(default="", max_length=200)
    problem_name_es: str = Field(default="", max_length=80)
    problem_name_en: str = Field(default="", max_length=80)


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
    #: Nombre del problema ({"es", "en"}) si es un mismo problema y el modelo dio los dos.
    nombre: dict[str, str] | None = None

    def a_json(self) -> dict[str, Any]:
        return {**asdict(self), "dominantes": list(self.dominantes)}

    @classmethod
    def de_json(cls, datos: Mapping[str, Any]) -> ResultadoCoherencia:
        return cls(datos["estado"], datos["motivo"], tuple(datos.get("dominantes") or ()),
                   datos.get("problema_dominante") or "", datos.get("nombre"))


class CoherenceCache(Protocol):
    """Resultados medidos de G0 por grupo y revisor (versión/modelo)."""

    def get(self, group_hash: str, checker: str) -> ResultadoCoherencia | None: ...

    def put(self, group_hash: str, checker: str, resultado: ResultadoCoherencia) -> None: ...


class InMemoryCoherenceCache:
    def __init__(self) -> None:
        self._datos: dict[tuple[str, str], dict[str, Any]] = {}

    def get(self, group_hash: str, checker: str) -> ResultadoCoherencia | None:
        guardado = self._datos.get((group_hash, checker))
        return ResultadoCoherencia.de_json(guardado) if guardado else None

    def put(self, group_hash: str, checker: str, resultado: ResultadoCoherencia) -> None:
        self._datos[(group_hash, checker)] = resultado.a_json()


def huella_del_grupo(frases: Mapping[str, str]) -> str:
    """Hash de los pares (id, frase) ordenados: el mismo grupo, la misma huella."""
    return hashlib.sha256(json.dumps(sorted(frases.items()), ensure_ascii=False).encode("utf-8")).hexdigest()


def _resultado(respuesta: CoherenceGroup, claves: Mapping[str, str]) -> ResultadoCoherencia:
    if respuesta.same_problem:
        nombre = ({"es": respuesta.problem_name_es.strip(), "en": respuesta.problem_name_en.strip()}
                  if respuesta.problem_name_es.strip() and respuesta.problem_name_en.strip() else None)
        return ResultadoCoherencia("mismo", respuesta.reason, nombre=nombre)
    dominantes = tuple(dict.fromkeys(claves[c] for c in respuesta.dominant_ids if c in claves))
    if len(dominantes) < MIN_DOMINANTES:
        dominantes = ()
    return ResultadoCoherencia("distinto", respuesta.reason, dominantes,
                               respuesta.dominant_problem if dominantes else "")


def comprobar_coherencia(grupos: Mapping[str, Mapping[str, str]], *, provider: JsonGenerator | None,
                         model: str | None, cache: CoherenceCache | None = None
                         ) -> dict[str, ResultadoCoherencia]:
    """{id del grupo: {id de la pieza: frase del problema}} → resultado por grupo,
    en una sola llamada con los grupos que no están en la caché."""
    if not grupos:
        return {}
    if provider is None or not model:
        return {g: ResultadoCoherencia("sin_comprobar", "sin proveedor del juez") for g in grupos}
    revisor = f"{COHERENCE_VERSION}/{model}"
    huellas = {g: huella_del_grupo(frases) for g, frases in grupos.items()}
    guardados = {g: r for g in grupos if cache is not None and (r := cache.get(huellas[g], revisor)) is not None}
    pendientes = {g: frases for g, frases in grupos.items() if g not in guardados}
    if not pendientes:
        return {g: guardados[g] for g in grupos}
    nuevos = _preguntar(pendientes, provider=provider, model=model)
    for g, resultado in nuevos.items():
        if cache is not None and resultado.estado != "sin_comprobar":
            cache.put(huellas[g], revisor, resultado)
    return {g: guardados.get(g) or nuevos[g] for g in grupos}


def _preguntar(grupos: Mapping[str, Mapping[str, str]], *, provider: JsonGenerator,
               model: str) -> dict[str, ResultadoCoherencia]:
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
