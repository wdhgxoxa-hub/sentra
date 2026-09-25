"""
Palabras prohibidas en lo que se ve (Fase 2, principio P1 de Walter)
====================================================================

«Cualquier persona, de un niño a alguien de cien años, debe entender cada
pantalla sin ayuda.» Estas palabras son jerga del proyecto o de la técnica y
no pueden aparecer en ningún texto visible; el detalle técnico va solo dentro
del desplegable «Ver detalle» (bloque `detalle` de i18n). Una sola lista: la
usan la guardia de i18n (tests/test_lenguaje_llano.py) y la del exe real
(tests/humo_exe.py, texto visible de cada pantalla).
"""

from __future__ import annotations

import re

#: (nombre, patrón). Sin distinguir mayúsculas; «G0»…«G9» y «e5» como palabra.
PROHIBIDAS: tuple[tuple[str, str], ...] = (
    ("tokens", r"\btokens?\b"),
    ("G0-G9", r"\bG\d\b"),
    ("cluster", r"\bclusters?\b"),
    ("pipeline", r"\bpipelines?\b"),
    ("regla N", r"\b(?:regla|rule)\s+\d"),
    ("LLM", r"\bLLMs?\b"),
    ("prompt", r"\bprompts?\b"),
    ("API", r"\bAPIs?\b"),
    ("JSON", r"\bJSON\b"),
    ("sidecar", r"\bsidecar\b"),
    ("uuid", r"\buuids?\b"),
    ("embedding", r"\bembeddings?\b"),
    ("e5", r"\be5\b"),
    ("backoff", r"\bbackoff\b"),
    ("OAuth", r"\bOAuth\b"),
    ("endpoint", r"\bendpoints?\b"),
    ("compuerta", r"\bcompuertas?\b"),
    ("gate", r"\bgates?\b"),
    ("run", r"\brun(?:Id|s)?\b"),
)

_PATRON = re.compile("|".join(f"(?P<p{n}>{p})" for n, (_, p) in enumerate(PROHIBIDAS)), re.IGNORECASE)


def palabras_prohibidas(texto: str) -> list[str]:
    """Los nombres de las prohibidas que aparecen en `texto`, en orden, sin repetir."""
    halladas: list[str] = []
    for m in _PATRON.finditer(texto):
        nombre = PROHIBIDAS[int(next(k for k, v in m.groupdict().items() if v is not None)[1:])][0]
        if nombre not in halladas:
            halladas.append(nombre)
    return halladas
