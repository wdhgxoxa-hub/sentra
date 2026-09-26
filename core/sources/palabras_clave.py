"""
Palabras clave propuestas para un escaneo (Fase 2, D1)
======================================================

La persona escribe el tema como lo contaría ("Facturas que los clientes no
pagan") y el asistente le propone las búsquedas en español e inglés, que
luego edita. Decisión de Walter:

- Con Gemini (A): una llamada del modelo general, registrada como
  `palabras_clave` en llm_usage y dentro de los topes del día.
- Sin Gemini (B), si no hay clave, no queda presupuesto o Gemini falla:
  términos con las palabras de contenido del tema, en su idioma. No traduce;
  el aviso de cobertura de la interfaz pide el otro idioma.

Una palabra clave es un TÉRMINO de 1 a 3 palabras («pdf a word»), no una frase
de queja: las fuentes exigen todas las palabras (HN, Stack Exchange,
Bluesky, Mastodon), la frase exacta (GitHub) o un nombre de tema (Product
Hunt), y las frases de queja ya las añade aparte la biblioteca de frases.
Escaneo 1 de la Fase 3 (25-09): con frases de 4-6 palabras, cinco fuentes
dieron 0; «pdf to word» da 215 en HN y 681 en GitHub (medido ese día).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, Field

from core.llm.base import JsonGenerator

from .sitios_stackexchange import SITIOS

Idioma = Literal["es", "en"]

#: Cuántas propone por idioma, el largo máximo de cada una y sus palabras.
MAX_POR_IDIOMA = 8
MAX_CARACTERES = 60
MAX_PALABRAS = 3
MAX_OUTPUT_TOKENS = 1_024
TIMEOUT_MS = 60_000
THINKING_BUDGET = 512

_COMUNES = {
    "es": {"de", "la", "el", "los", "las", "que", "no", "con", "para", "por", "y", "en", "un", "una",
           "mi", "sin", "cómo", "como", "del", "al", "se", "a", "lo", "su", "sus", "mis"},
    "en": {"the", "and", "to", "of", "with", "my", "for", "is", "a", "an", "who", "how", "in", "on",
           "not", "without", "that", "their"},
}
_ACENTOS = re.compile(r"[áéíóúñ¿¡]", re.IGNORECASE)

class PalabrasPropuestas(BaseModel):
    """Búsquedas propuestas por idioma. Es también el esquema que se pide a Gemini."""

    es: list[str] = Field(default_factory=list)
    en: list[str] = Field(default_factory=list)
    #: Medida B (Fase 3), en la misma llamada: ¿el tema es de software? None = no se sabe.
    tipo: Literal["software", "otro"] | None = None
    #: Sitios de Stack Exchange adecuados al tema, del catálogo cerrado (sitios_stackexchange.py).
    sitios_stackexchange: list[str] = Field(default_factory=list)


def idioma_del_tema(tema: str) -> Idioma:
    """Español o inglés por sus palabras comunes y sus acentos. Ante la duda, español."""
    palabras = re.findall(r"[\wáéíóúñ]+", tema.lower())
    puntos = {idioma: sum(p in comunes for p in palabras) for idioma, comunes in _COMUNES.items()}
    if _ACENTOS.search(tema):
        puntos["es"] += 1
    return "en" if puntos["en"] > puntos["es"] else "es"


def _limpias(frases: Iterable[str]) -> list[str]:
    """Sin vacías, sin repetidas (ignorando mayúsculas y espacios) y sin las
    largas: más de 60 caracteres o más de 3 palabras."""
    vistas: set[str] = set()
    limpias: list[str] = []
    for frase in frases:
        normal = " ".join(frase.split())
        clave = normal.lower()
        if not normal or len(normal) > MAX_CARACTERES or len(normal.split()) > MAX_PALABRAS or clave in vistas:
            continue
        vistas.add(clave)
        limpias.append(normal)
    return limpias[:MAX_POR_IDIOMA]


def proponer_sin_gemini(tema: str, idiomas: Sequence[str]) -> PalabrasPropuestas:
    """Términos cortos con las palabras de contenido del tema (sin artículos ni
    nexos), en su idioma si es uno de los elegidos: las tres primeras, las dos
    primeras y cada pareja seguida."""
    idioma = idioma_del_tema(tema)
    if idioma not in idiomas:
        return PalabrasPropuestas()
    contenido = [p for p in re.findall(r"[\wáéíóúñ]+", tema.lower()) if p not in _COMUNES[idioma]]
    terminos = [" ".join(contenido[:3]), " ".join(contenido[:2])]
    terminos += [" ".join(contenido[i:i + 2]) for i in range(len(contenido) - 1)]
    limpias = _limpias(terminos)
    return PalabrasPropuestas(es=limpias) if idioma == "es" else PalabrasPropuestas(en=limpias)


def _prompt(tema: str, idiomas: Sequence[str]) -> str:
    nombres = {"es": "español", "en": "inglés"}
    pedidos = " y ".join(nombres[i] for i in idiomas if i in nombres)
    return (
        "Eres un asistente que prepara búsquedas en foros y redes (Hacker News, Stack Exchange, "
        "GitHub, YouTube, Bluesky, Mastodon) para encontrar a personas que se quejan de un problema.\n"
        f"Tema que describe la persona: «{tema}».\n"
        f"Propón entre 5 y {MAX_POR_IDIOMA} términos de búsqueda de 1 a 3 palabras en {pedidos}: "
        "la tarea o el objeto del problema tal como lo nombra la gente (por ejemplo «pdf a word», "
        "«convertir pdf»), no frases de queja: las frases de queja las añade SENTRA aparte, y los "
        "buscadores exigen todas las palabras. Nada de nombres de productos. "
        "Cada idioma con sus propias expresiones naturales, no traducciones literales. "
        "Deja vacía la lista de un idioma no pedido.\n"
        # Medida B (Fase 3): en la misma llamada, qué fuentes encajan con el tema.
        "Di también si el tema es de software (tipo «software»: programar, usar o construir "
        "herramientas informáticas) o de otra cosa (tipo «otro»: un negocio, un trabajo, la vida "
        "diaria). Y elige, SOLO de esta lista, los sitios de Stack Exchange donde la gente "
        "hablaría de este problema (sitios_stackexchange; vacía si ninguno encaja): "
        + "; ".join(f"{clave} ({nombre})" for clave, nombre in SITIOS.items()) + "."
    )


def proponer_con_gemini(proveedor: JsonGenerator, modelo: str, tema: str,
                        idiomas: Sequence[str]) -> PalabrasPropuestas:
    """Una llamada a Gemini (`palabras_clave`). Las excepciones del proveedor
    (sin presupuesto, error) suben: quien llama decide el respaldo."""
    propuesta = proveedor.generate_json(
        _prompt(tema, idiomas), PalabrasPropuestas, model=modelo, max_output_tokens=MAX_OUTPUT_TOKENS,
        timeout_ms=TIMEOUT_MS, purpose="palabras_clave", thinking_budget=THINKING_BUDGET)
    return PalabrasPropuestas(es=_limpias(propuesta.es) if "es" in idiomas else [],
                              en=_limpias(propuesta.en) if "en" in idiomas else [],
                              tipo=propuesta.tipo,
                              sitios_stackexchange=list(dict.fromkeys(
                                  s for s in propuesta.sitios_stackexchange if s in SITIOS)))
