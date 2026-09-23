"""Texto plano a partir del HTML que devuelven algunas APIs (HN, Discourse, Stack Exchange)."""

from __future__ import annotations

import html
from html.parser import HTMLParser

#: Etiquetas que separan párrafos o líneas.
_PARRAFO = frozenset({"p", "div", "blockquote", "pre", "ul", "ol", "h1", "h2", "h3", "h4"})
_LINEA = frozenset({"br", "li", "tr"})


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _PARRAFO:
            self.partes.append("\n\n")
        elif tag in _LINEA:
            self.partes.append("\n")

    def handle_data(self, data: str) -> None:
        self.partes.append(data)


def html_to_text(fragmento: str | None) -> str:
    """El texto legible de un fragmento HTML: sin etiquetas y con entidades resueltas."""
    if not fragmento:
        return ""
    extractor = _Extractor()
    extractor.feed(fragmento)
    extractor.close()
    texto = html.unescape("".join(extractor.partes))
    lineas = [" ".join(linea.split()) for linea in texto.split("\n")]
    # Como mucho una línea en blanco seguida.
    salida: list[str] = []
    for linea in lineas:
        if not linea and salida and not salida[-1]:
            continue
        salida.append(linea)
    return "\n".join(salida).strip()
