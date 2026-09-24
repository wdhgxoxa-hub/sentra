"""
Documento en PDF (AUD-008, Fase E)
==================================

Pinta en un PDF A4 un `DocumentModel` (el dossier o el plan): portada,
índice con números de página y las secciones del modelo, en su orden. El
contenido no se decide aquí: sale de `core.documents.model`, el mismo del que
sale el Markdown, así que los dos formatos dicen lo mismo. Se genera en el
sidecar con ReportLab; Rust solo pide los bytes y los guarda donde elija
quien lo exporta.

Lo propio del PDF:

- **Datos de demostración, a la vista.** Si la procedencia es de
  demostración, cada página lleva la marca de agua diagonal.
- **Franja «no recomendado».** Un plan forzado sin veredicto CONSTRUIR la
  lleva arriba en cada página.
- **Fuente incrustada.** Bitstream Vera (fonts/, con su licencia): cubre
  tildes, ñ, ¿, ¡, «», — y …, así que el texto se extrae igual que se lee.
  Los bloques de código del plan usan Courier, que solo cubre Latin-1.
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from core.documents.model import Block, DocumentModel, textos

FUENTES = Path(__file__).resolve().parent / "fonts"
SANS = "SentraSans"
SANS_BOLD = "SentraSans-Bold"
SANS_ITALIC = "SentraSans-Italic"
MONO = "Courier"

MARGEN = 2 * cm
ESTILO_SECCION = "SentraSeccion"

# --- Fuentes -----------------------------------------------------------------

def _registrar_fuentes() -> None:
    """Registra Vera una sola vez por proceso."""
    if SANS in pdfmetrics.getRegisteredFontNames():
        return
    pdfmetrics.registerFont(TTFont(SANS, str(FUENTES / "Vera.ttf")))
    pdfmetrics.registerFont(TTFont(SANS_BOLD, str(FUENTES / "VeraBd.ttf")))
    pdfmetrics.registerFont(TTFont(SANS_ITALIC, str(FUENTES / "VeraIt.ttf")))
    pdfmetrics.registerFontFamily(
        SANS, normal=SANS, bold=SANS_BOLD, italic=SANS_ITALIC, boldItalic=SANS_BOLD
    )


def _estilos() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("SentraCuerpo", fontName=SANS, fontSize=10, leading=14)
    estilos = {
        "cuerpo": base,
        "portada": ParagraphStyle(
            "SentraPortada", parent=base, fontName=SANS_BOLD, fontSize=22,
            leading=28, alignment=TA_CENTER, spaceAfter=24,
        ),
        "seccion": ParagraphStyle(
            ESTILO_SECCION, parent=base, fontName=SANS_BOLD, fontSize=15,
            leading=20, spaceBefore=6, spaceAfter=10,
        ),
        "sub": ParagraphStyle(
            "SentraSub", parent=base, fontName=SANS_BOLD, fontSize=11.5,
            leading=16, spaceBefore=8, spaceAfter=4,
        ),
        "cita": ParagraphStyle(
            "SentraCita", parent=base, fontName=SANS_ITALIC, leftIndent=12,
            spaceBefore=6,
        ),
        "firma": ParagraphStyle(
            "SentraFirma", parent=base, fontSize=8.5, leading=11,
            textColor=colors.HexColor("#555555"), leftIndent=12, spaceAfter=6,
        ),
        "vineta": ParagraphStyle(
            "SentraVineta", parent=base, leftIndent=14, bulletIndent=4,
        ),
        "nota": ParagraphStyle(
            "SentraNota", parent=base, fontSize=9, leading=12,
            textColor=colors.HexColor("#8a5a00"), spaceBefore=6,
        ),
        "codigo": ParagraphStyle(
            "SentraCodigo", parent=base, fontName=MONO, fontSize=8, leading=10,
            leftIndent=8,
        ),
        "toc": ParagraphStyle("SentraToc", parent=base, fontSize=11, leading=18),
    }
    # El título del índice se ve como una sección, pero con otro nombre de
    # estilo: si no, el índice se listaría a sí mismo.
    estilos["indice"] = ParagraphStyle("SentraIndice", parent=estilos["seccion"])
    return estilos


def _p(texto: str, estilo: ParagraphStyle) -> Paragraph:
    """Párrafo con el texto escapado: los datos no pueden romper el marcado."""
    return Paragraph(escape(texto), estilo)


# --- Plantilla -----------------------------------------------------------------

class _Documento(BaseDocTemplate):
    """Plantilla A4 que alimenta el índice con los títulos de sección."""

    def __init__(self, destino: io.BytesIO, titulo: str) -> None:
        super().__init__(
            destino, pagesize=A4, leftMargin=MARGEN, rightMargin=MARGEN,
            topMargin=MARGEN + 0.4 * cm, bottomMargin=MARGEN, title=titulo,
            author="SENTRA",
        )
        marco = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="cuerpo")
        self.addPageTemplates([PageTemplate(id="pagina", frames=[marco])])

    def afterFlowable(self, flowable: Flowable) -> None:
        if isinstance(flowable, Paragraph) and flowable.style.name == ESTILO_SECCION:
            self.notify("TOCEntry", (0, flowable.getPlainText(), self.page))


def _canvas_numerado(titulo: str, pie: str, marca_de_agua: str | None,
                     franja: str | None) -> type:
    """
    Canvas que dibuja encabezado, pie «página X de Y» y, si procede, la marca
    de agua y la franja. Guarda cada página y las pinta al cerrar, cuando ya
    se sabe el total.
    """

    class Numerado(rl_canvas.Canvas):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._paginas: list[dict[str, Any]] = []

        def showPage(self) -> None:
            self._paginas.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            total = len(self._paginas)
            for estado in self._paginas:
                self.__dict__.update(estado)
                self._decorar(total)
                super().showPage()
            super().save()

        def _decorar(self, total: int) -> None:
            ancho, alto = A4
            self.saveState()
            if marca_de_agua:
                self.setFont(SANS_BOLD, 34)
                self.setFillColor(colors.Color(0.8, 0.1, 0.1, alpha=0.18))
                self.translate(ancho / 2, alto / 2)
                self.rotate(45)
                self.drawCentredString(0, 0, marca_de_agua)
                self.rotate(-45)
                self.translate(-ancho / 2, -alto / 2)
            if franja:
                self.setFillColor(colors.HexColor("#b3261e"))
                self.rect(0, alto - 1.1 * cm, ancho, 1.1 * cm, stroke=0, fill=1)
                self.setFillColor(colors.white)
                self.setFont(SANS_BOLD, 9)
                self.drawCentredString(ancho / 2, alto - 0.7 * cm, franja[:120])
            self.setFillColor(colors.HexColor("#555555"))
            self.setFont(SANS, 8.5)
            self.drawString(MARGEN, alto - MARGEN + 0.2 * cm, titulo)
            self.drawRightString(
                ancho - MARGEN, MARGEN - 0.9 * cm,
                pie.format(n=self._pageNumber, total=total),
            )
            self.restoreState()

    return Numerado


# --- Secciones -----------------------------------------------------------------

def _flowables(bloque: Block, estilos: Mapping[str, ParagraphStyle]) -> list[Flowable]:
    """Un bloque del modelo en elementos de ReportLab."""
    if bloque.kind == "paragraph":
        return [_p(bloque.text, estilos["cuerpo"])]
    if bloque.kind == "note":
        return [_p(bloque.text, estilos["nota"])]
    if bloque.kind == "subheading":
        return [_p(bloque.text, estilos["sub"])]
    if bloque.kind == "bullets":
        return [Paragraph(escape(item), estilos["vineta"], bulletText="•")
                for item in bloque.items]
    if bloque.kind == "quote":
        return [_p(bloque.text, estilos["cita"]), _p(bloque.signature, estilos["firma"])]
    if bloque.kind == "table":
        return [_tabla(bloque.rows, estilos)]
    return [Preformatted(bloque.text, estilos["codigo"])]


def _tabla(filas: Sequence[tuple[str, str]], estilos: Mapping[str, ParagraphStyle]) -> Table:
    tabla = Table(
        [[_p(k, estilos["cuerpo"]), _p(v, estilos["cuerpo"])] for k, v in filas],
        colWidths=[5.5 * cm, None],
    )
    tabla.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        ("FONTNAME", (0, 0), (0, -1), SANS_BOLD),
    ]))
    return tabla


# --- Entrada pública -----------------------------------------------------------

def render_pdf(documento: DocumentModel) -> bytes:
    """El documento en PDF: portada, índice, procedencia y secciones."""
    _registrar_fuentes()
    rotulos = textos(documento.language)
    estilos = _estilos()

    historia: list[Flowable] = []

    # Portada
    historia += [Spacer(1, 4 * cm), _p(documento.title, estilos["portada"])]
    historia.append(_tabla(list(documento.cover), estilos))
    historia.append(PageBreak())

    # Índice
    indice = TableOfContents()
    indice.levelStyles = [estilos["toc"]]
    historia += [_p(rotulos["index"], estilos["indice"]), indice, PageBreak()]

    # La procedencia va antes que nada (AUD-009).
    if documento.source_notice:
        historia.append(_p(documento.source_notice, estilos["nota"]))

    for seccion in documento.sections:
        historia.append(_p(seccion.title, estilos["seccion"]))
        for bloque in seccion.blocks:
            historia += _flowables(bloque, estilos)

    destino = io.BytesIO()
    titulo = f"SENTRA · {documento.title}"
    _Documento(destino, titulo).multiBuild(
        historia,
        canvasmaker=_canvas_numerado(titulo[:110], rotulos["page"], documento.watermark,
                                     documento.stripe),
    )
    return destino.getvalue()
