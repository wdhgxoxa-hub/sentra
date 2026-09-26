"""
Identificadores de autor fuera de lo que se ve (R9, Fase 3)
===========================================================

Los autores solo existen como hash (author_hash) y dentro de un veredicto como
seudónimo (author_key). Pero el id de una pieza de Bluesky lleva el DID de su
autor y los textos citan a otras personas con @usuario: nada de eso puede
llegar a la interfaz ni a los documentos. Escaneo 2 de la Fase 3 (25-09): el
nombre de un grupo descartado mostraba «bluesky:did:plc:…».

`ocultar_identificadores` se aplica a todo texto de una pieza antes de
enseñarlo. Las direcciones del original (R5) siguen D-M12 (Walter, Fase 3): se
guardan completas, con el DID de Bluesky, y se ven con `direccion_visible`; la
completa solo va en el destino de un enlace.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

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


#: Una dirección dentro de un texto (la firma de una cita).
DIRECCION = re.compile(r"https?://\S+")


def direccion_visible(url: str) -> str:
    """La dirección tal como se ve (D-M12): sin protocolo y sin la cuenta del autor.

    Se guarda completa (R5: sin ella no se verifica la evidencia), pero la cuenta
    nunca se ve como texto (R9): el tramo tras `/profile/` de Bluesky y cualquier
    tramo que lleve un DID, un at:// o un @usuario se ven como «…». La completa solo va en el
    destino de un enlace. Igual que `direccionVisible` de la interfaz.
    """
    partes = urlsplit(url)
    if not partes.scheme or not partes.netloc:
        return url
    tramos = partes.path.split("/")
    visibles = ["…" if IDENTIFICADOR_DE_AUTOR.search(unquote(t)) or (partes.hostname == "bsky.app" and i > 0
                                                       and tramos[i - 1] == "profile" and t) else t
                for i, t in enumerate(tramos)]
    consulta = f"?{partes.query}" if partes.query else ""
    return f"{partes.netloc}{'/'.join(visibles)}{consulta}"




#: Cuentas sin ambigüedad (DID y at://). El @usuario no: en un plan, «@tanstack/query»
#: es un paquete de npm; en la evidencia ya lo oculta `ocultar_identificadores`.
CUENTA = re.compile(r"at://\S+|\bdid:(?:plc|web|key):[A-Za-z0-9._%:-]+")


def ocultar_cuentas(texto: str) -> str:
    """El texto con cada DID o at:// como «[cuenta]»."""
    return CUENTA.sub("[cuenta]", texto)


def trozos_visibles(texto: str) -> list[tuple[str, str | None]]:
    """(lo que se ve, destino) de un texto que se pinta (D-M12): las direcciones como
    enlace (se ve `direccion_visible`, la completa va en el destino) y el resto sin
    cuentas. Sirve para lo guardado antes de los alias sin reescribirlo."""
    trozos: list[tuple[str, str | None]] = []
    inicio = 0
    for m in DIRECCION.finditer(texto):
        if m.start() > inicio:
            trozos.append((ocultar_cuentas(texto[inicio:m.start()]), None))
        trozos.append((direccion_visible(m.group(0)), m.group(0)))
        inicio = m.end()
    if inicio < len(texto):
        trozos.append((ocultar_cuentas(texto[inicio:]), None))
    return trozos


def visible_en_markdown(texto: str) -> str:
    """Texto de un documento en Markdown: enlaces [visible](completa) y sin cuentas."""
    return "".join(f"[{visto}]({destino})" if destino else visto for visto, destino in trozos_visibles(texto))
