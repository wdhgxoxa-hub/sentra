"""
Documento entregable en PDF (AUD-008)
=====================================

Pinta en un PDF A4 el `DocumentModel` de una oportunidad (D-H): portada,
índice con números de página y las diez secciones del modelo, en su orden.
El contenido no se decide aquí: sale de `core.documents.model`, el mismo
del que la interfaz pinta el PRD, así que lo que se ve y lo que se exporta
coinciden. Se genera en el sidecar con ReportLab; Rust solo pide los bytes y
los guarda donde elija quien lo exporta.

Lo propio del PDF:

- **Datos de demostración, a la vista.** Si la fuente es el corpus
  fabricado, cada página lleva la marca de agua diagonal.
- **Fuente incrustada.** Bitstream Vera (fonts/, con su licencia): cubre
  tildes, ñ, ¿, ¡, «», — y …, así que el texto se extrae igual que se lee.
  Los bloques de código del plan usan Courier, que solo cubre Latin-1.
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from datetime import datetime
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

from core.documents.model import TEXTOS, Block, build_document

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


def _canvas_numerado(titulo: str, pie: str, marca_de_agua: str | None) -> type:
    """
    Canvas que dibuja encabezado, pie «página X de Y» y, si procede, la marca
    de agua. Guarda cada página y las pinta al cerrar, cuando ya se sabe el
    total.
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

def _markdown(texto: str, estilos: Mapping[str, ParagraphStyle]) -> list[Flowable]:
    """Pinta el Markdown del plan: títulos, viñetas, bloques de código y tablas."""
    salida: list[Flowable] = []
    en_codigo = False
    codigo: list[str] = []
    for linea in texto.splitlines():
        if linea.strip().startswith("```"):
            if en_codigo:
                salida.append(Preformatted("\n".join(codigo), estilos["codigo"]))
                codigo = []
            en_codigo = not en_codigo
            continue
        if en_codigo or linea.strip().startswith("|"):
            if en_codigo:
                codigo.append(linea)
            else:
                salida.append(Preformatted(linea, estilos["codigo"]))
            continue
        limpio = linea.strip().replace("**", "").replace("`", "")
        if not limpio:
            continue
        if limpio.startswith("#"):
            salida.append(_p(limpio.lstrip("#").strip(), estilos["sub"]))
        elif limpio[:2] in ("- ", "* "):
            salida.append(Paragraph(escape(limpio[2:]), estilos["vineta"], bulletText="•"))
        else:
            salida.append(_p(limpio, estilos["cuerpo"]))
    if codigo:
        salida.append(Preformatted("\n".join(codigo), estilos["codigo"]))
    return salida


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
    return _markdown(bloque.text, estilos)


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

def build_pdf(
    cluster: Mapping[str, Any],
    language: str,
    architecture: str | None = None,
    version: str = "",
    generated_at: datetime | None = None,
) -> bytes:
    """
    Documento PDF de una oportunidad.

    Args:
        cluster: la oportunidad tal como la serializa Rust (o PostgreSQL).
        language: "es" o "en"; cualquier otro cae a "es".
        architecture: Markdown del plan de Gemini, si se generó en la sesión.
        version: versión de SENTRA que genera el documento.
        generated_at: instante de generación (por defecto, ahora en UTC).
    """
    _registrar_fuentes()
    modelo = build_document(cluster, language, architecture=architecture,
                            version=version, generated_at=generated_at)
    textos = TEXTOS[modelo.language]
    estilos = _estilos()

    historia: list[Flowable] = []

    # Portada
    historia += [Spacer(1, 4 * cm), _p(modelo.label, estilos["portada"])]
    historia.append(_tabla(list(modelo.cover), estilos))
    historia.append(PageBreak())

    # Índice
    indice = TableOfContents()
    indice.levelStyles = [estilos["toc"]]
    historia += [_p(textos["index"], estilos["indice"]), indice, PageBreak()]

    # La fuente de los datos va antes que nada (AUD-009).
    historia.append(_p(modelo.source_notice, estilos["nota"]))

    # Las diez secciones, en el orden del modelo.
    for seccion in modelo.sections:
        historia.append(_p(seccion.title, estilos["seccion"]))
        for bloque in seccion.blocks:
            historia += _flowables(bloque, estilos)

    destino = io.BytesIO()
    titulo = f"SENTRA · {textos['doc']} · {modelo.label}"
    documento = _Documento(destino, titulo)
    documento.multiBuild(
        historia,
        canvasmaker=_canvas_numerado(
            titulo[:110], textos["page"],
            textos["watermark"] if modelo.data_source == "demo" else None,
        ),
    )
    return destino.getvalue()
