"""
Identificadores de autor fuera de lo que se ve (R9, Fase 3)
===========================================================

Los autores solo existen como hash (author_hash) y dentro de un veredicto como
seudónimo (author_key). Pero el id de una pieza de Bluesky lleva el DID de su
autor y los textos citan a otras personas con @usuario: nada de eso puede
llegar a la interfaz ni a los documentos. Escaneo 2 de la Fase 3 (25-09): el
nombre de un grupo descartado mostraba «bluesky:did:plc:…».

`ocultar_identificadores` se aplica a todo texto de una pieza antes de
enseñarlo. Las direcciones del original (R5) no pasan por aquí: la de Bluesky
lleva el DID y enlazar sin él no es posible (decisión pendiente de Walter).
"""

from __future__ import annotations

import re

#: DID de AT Protocol (did:plc:…, did:web:…), URI at:// y @usuario (no correos:
#: la arroba va al principio o tras un espacio o un signo).
IDENTIFICADOR_DE_AUTOR = re.compile(
    r"at://\S+"
    r"|\bdid:(?:plc|web|key):[A-Za-z0-9._%:-]+"
    r"|(?<![\w.@])@[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?"
)


def _sustituto(m: re.Match[str]) -> str:
    return "[usuario]" if m.group(0).startswith("@") else "[cuenta]"


def ocultar_identificadores(texto: str) -> str:
    """El texto con cada DID o at:// sustituido por «[cuenta]» y cada @usuario por «[usuario]»."""
    return IDENTIFICADOR_DE_AUTOR.sub(_sustituto, texto)
