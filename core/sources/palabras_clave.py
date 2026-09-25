"""
Palabras clave propuestas para un escaneo (Fase 2, D1)
======================================================

La persona escribe el tema como lo contaría ("Facturas que los clientes no
pagan") y el asistente le propone las búsquedas en español e inglés, que
luego edita. Decisión de Walter:

- Con Gemini (A): una llamada del modelo general, registrada como
  `palabras_clave` en llm_usage y dentro de los topes del día.
- Sin Gemini (B), si no hay clave, no queda presupuesto o Gemini falla:
  plantillas de queja en el idioma en que está escrito el tema. No traduce;
  el aviso de cobertura de la interfaz pide el otro idioma.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, Field

from core.llm.base import JsonGenerator

Idioma = Literal["es", "en"]

#: Cuántas propone por idioma y el largo máximo de cada una: son búsquedas.
MAX_POR_IDIOMA = 8
MAX_CARACTERES = 60
MAX_OUTPUT_TOKENS = 1_024
TIMEOUT_MS = 60_000
THINKING_BUDGET = 512

_COMUNES = {
    "es": {"de", "la", "el", "los", "las", "que", "no", "con", "para", "por", "y", "en", "un", "una",
           "mi", "sin", "cómo", "como", "del", "al", "se"},
    "en": {"the", "and", "to", "of", "with", "my", "for", "is", "a", "an", "who", "how", "in", "on",
           "not", "without", "that", "their"},
}
_ACENTOS = re.compile(r"[áéíóúñ¿¡]", re.IGNORECASE)

_PLANTILLAS: dict[str, tuple[str, ...]] = {
    "es": ("{tema}", "problema con {tema}", "{tema} no funciona", "cómo resolver {tema}", "harto de {tema}"),
    "en": ("{tema}", "{tema} problem", "{tema} not working", "how to fix {tema}", "tired of {tema}"),
}


class PalabrasPropuestas(BaseModel):
    """Búsquedas propuestas por idioma. Es también el esquema que se pide a Gemini."""

    es: list[str] = Field(default_factory=list)
    en: list[str] = Field(default_factory=list)


def idioma_del_tema(tema: str) -> Idioma:
    """Español o inglés por sus palabras comunes y sus acentos. Ante la duda, español."""
    palabras = re.findall(r"[\wáéíóúñ]+", tema.lower())
    puntos = {idioma: sum(p in comunes for p in palabras) for idioma, comunes in _COMUNES.items()}
    if _ACENTOS.search(tema):
        puntos["es"] += 1
    return "en" if puntos["en"] > puntos["es"] else "es"


def _limpias(frases: Iterable[str]) -> list[str]:
    """Sin vacías, sin repetidas (ignorando mayúsculas y espacios) y sin las largas."""
    vistas: set[str] = set()
    limpias: list[str] = []
    for frase in frases:
        normal = " ".join(frase.split())
        clave = normal.lower()
        if not normal or len(normal) > MAX_CARACTERES or clave in vistas:
            continue
        vistas.add(clave)
        limpias.append(normal)
    return limpias[:MAX_POR_IDIOMA]


def proponer_sin_gemini(tema: str, idiomas: Sequence[str]) -> PalabrasPropuestas:
    """Plantillas de queja en el idioma del tema, si es uno de los elegidos."""
    idioma = idioma_del_tema(tema)
    if idioma not in idiomas:
        return PalabrasPropuestas()
    base = " ".join(tema.lower().split())
    frases = _limpias(p.format(tema=base) for p in _PLANTILLAS[idioma])
    return PalabrasPropuestas(**{idioma: frases})


def _prompt(tema: str, idiomas: Sequence[str]) -> str:
    nombres = {"es": "español", "en": "inglés"}
    pedidos = " y ".join(nombres[i] for i in idiomas if i in nombres)
    return (
        "Eres un asistente que prepara búsquedas en foros y redes (Hacker News, Stack Exchange, "
        "GitHub, YouTube, Bluesky, Mastodon) para encontrar a personas que se quejan de un problema.\n"
        f"Tema que describe la persona: «{tema}».\n"
        f"Propón entre 5 y {MAX_POR_IDIOMA} búsquedas cortas (2 a 5 palabras) en {pedidos}, "
        "con las palabras que usaría alguien al quejarse de ese problema, no nombres de productos. "
        "Cada idioma con sus propias expresiones naturales, no traducciones literales. "
        "Deja vacía la lista de un idioma no pedido."
    )


def proponer_con_gemini(proveedor: JsonGenerator, modelo: str, tema: str,
                        idiomas: Sequence[str]) -> PalabrasPropuestas:
    """Una llamada a Gemini (`palabras_clave`). Las excepciones del proveedor
    (sin presupuesto, error) suben: quien llama decide el respaldo."""
    propuesta = proveedor.generate_json(
        _prompt(tema, idiomas), PalabrasPropuestas, model=modelo, max_output_tokens=MAX_OUTPUT_TOKENS,
        timeout_ms=TIMEOUT_MS, purpose="palabras_clave", thinking_budget=THINKING_BUDGET)
    return PalabrasPropuestas(es=_limpias(propuesta.es) if "es" in idiomas else [],
                              en=_limpias(propuesta.en) if "en" in idiomas else [])
