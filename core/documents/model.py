"""
Modelo de documento (Fase E)
============================

El dossier y el plan de construcción se componen como un `DocumentModel`:
portada, aviso de procedencia, franja opcional y secciones hechas de bloques.
Cada salida solo lo pinta: el PDF con ReportLab (`pdf_report.render_pdf`) y
el Markdown para un agente (`to_markdown`). Así lo que se exporta en uno y
otro formato es el mismo documento.

Los avisos, la franja «no recomendado» y la marca de agua de datos de
demostración los pone el código a partir de los datos (D de la Fase E); el
contenido de mercado llega ya verificado (`core/documents/claims.py`).

El documento antiguo por cluster (diez secciones a partir del PRD
determinista de `blueprint`) se retiró con la pipeline antigua (AUD-049).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

BlockKind = Literal["paragraph", "note", "subheading", "bullets", "quote", "table", "code"]
DocumentKind = Literal["dossier", "plan"]

#: Rótulos que pone el código, por idioma.
TEXTOS: dict[str, dict[str, str]] = {
    "es": {
        "index": "Índice",
        "page": "página {n} de {total}",
        "watermark": "DATOS DE DEMOSTRACIÓN — NO REALES",
    },
    "en": {
        "index": "Contents",
        "page": "page {n} of {total}",
        "watermark": "DEMO DATA — NOT REAL",
    },
}


def textos(language: str) -> dict[str, str]:
    """Rótulos del idioma pedido; cualquier otro cae a español."""
    return TEXTOS.get(language, TEXTOS["es"])


@dataclass(frozen=True)
class Block:
    """Un bloque de contenido. Cada salida decide cómo pintar cada tipo."""

    kind: BlockKind
    text: str = ""
    items: tuple[str, ...] = ()
    signature: str = ""
    rows: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class DocumentModel:
    """El documento entero, en un idioma."""

    language: str
    kind: DocumentKind
    title: str
    #: "real", "demo" o None (procedencia desconocida).
    data_source: str | None
    cover: tuple[tuple[str, str], ...]
    #: De dónde salen los datos, en una frase: va antes que nada.
    source_notice: str = ""
    #: Franja que va en cada página (plan forzado sin veredicto CONSTRUIR).
    stripe: str | None = None
    sections: tuple[Section, ...] = field(default_factory=tuple)

    @property
    def watermark(self) -> str | None:
        """Marca de agua en cada página, solo con datos de demostración."""
        return textos(self.language)["watermark"] if self.data_source == "demo" else None

    def to_markdown(self) -> str:
        """El documento en Markdown, para un agente o para copiarlo.

        Primero la franja (si la hay), después la procedencia (con la marca
        de demostración si procede) y el título; la franja se repite al
        empezar cada sección, igual que en cada página del PDF.
        """
        franja = f"> **{self.stripe}**" if self.stripe else ""
        aviso = " ".join(t for t in (self.watermark, self.source_notice) if t)
        partes = [franja, f"> {aviso}" if aviso else "", f"# {self.title}"]
        for seccion in self.sections:
            partes += [f"## {seccion.title}", franja]
            partes += [_markdown_de(bloque) for bloque in seccion.blocks]
        return "\n\n".join(p for p in partes if p) + "\n"


def _markdown_de(bloque: Block) -> str:
    if bloque.kind == "paragraph":
        return bloque.text
    if bloque.kind == "note":
        return f"> {bloque.text}"
    if bloque.kind == "subheading":
        return f"### {bloque.text}"
    if bloque.kind == "bullets":
        return "\n".join(f"- {item}" for item in bloque.items)
    if bloque.kind == "quote":
        return f"> {bloque.text}\n>\n> — {bloque.signature}"
    if bloque.kind == "code":
        return f"```\n{bloque.text}\n```"
    filas = ["| | |", "|---|---|", *(f"| {k} | {v} |" for k, v in bloque.rows)]
    return "\n".join(filas)
