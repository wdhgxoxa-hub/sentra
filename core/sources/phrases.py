"""
Biblioteca de frases de intención de dolor (F2.5)
=================================================

Frases literales con las que la gente escribe un dolor que vale la pena
resolver. Se combinan con el tema del perfil en la búsqueda de cada fuente.
Versionada: cada escaneo guarda la versión con la que buscó, para que un
veredicto se pueda rastrear hasta las frases que lo trajeron.

Cambiar una frase = subir la versión.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

PHRASE_LIBRARY_VERSION = "2026-09-23.v1"

Intent = Literal[
    "busca_herramienta", "frustracion", "parche_casero", "dispuesto_a_pagar", "alternativa",
]

INTENTS: tuple[Intent, ...] = (
    "busca_herramienta", "frustracion", "parche_casero", "dispuesto_a_pagar", "alternativa",
)

PHRASES: dict[Intent, dict[str, tuple[str, ...]]] = {
    "busca_herramienta": {
        "en": ("is there a tool", "is there an app", "looking for a tool",
               "any software that", "how do you automate"),
        "es": ("existe alguna herramienta", "hay alguna app", "busco una herramienta",
               "algún programa que", "cómo automatizan"),
    },
    "frustracion": {
        "en": ("I hate", "so annoying", "drives me crazy", "waste hours", "such a pain"),
        "es": ("odio", "me desespera", "es un dolor de cabeza", "pierdo horas", "qué frustración"),
    },
    "parche_casero": {
        "en": ("I use a spreadsheet", "wrote a script", "manual workaround",
               "copy and paste every", "by hand every"),
        "es": ("uso una hoja de cálculo", "hice un script", "lo hago a mano",
               "copio y pego cada", "un apaño"),
    },
    "dispuesto_a_pagar": {
        "en": ("I'd pay", "worth paying", "would pay for", "happy to pay", "take my money"),
        "es": ("pagaría", "vale la pena pagar", "pagaría por", "estoy dispuesto a pagar",
               "tomen mi dinero"),
    },
    "alternativa": {
        "en": ("alternative to", "replacement for", "switching from", "cheaper than", "instead of"),
        "es": ("alternativa a", "reemplazo de", "cambiarme de", "más barato que", "en vez de"),
    },
}


def phrases_for(intents: Iterable[Intent], languages: Iterable[str]) -> list[str]:
    """Las frases de esas intenciones en esos idiomas, sin repetir y en orden."""
    idiomas = list(languages)
    vistas: dict[str, None] = {}
    for intencion in intents:
        for idioma in idiomas:
            for frase in PHRASES[intencion].get(idioma, ()):
                vistas.setdefault(frase, None)
    return list(vistas)
