"""
Documento entregable en PDF (AUD-008)
=====================================

Convierte una oportunidad en un PDF A4 listo para enviar: portada, índice
con números de página y diez secciones fijas. Se genera en el sidecar con
ReportLab; Rust solo pide los bytes y los guarda donde elija quien lo exporta.

Reglas que sostienen el documento:

- **Nada inventado.** Cada sección sale del problema guardado (cifras,
  citas, comunidades) o del PRD determinista (`blueprint.build_blueprint`).
  Lo que no existe se dice: el plan de Gemini «No generado», una cita sin
  fecha «fecha no registrada».
- **Datos de demostración, a la vista.** Si la fuente es el corpus
  fabricado, cada página lleva la marca de agua diagonal.
- **Un solo idioma.** Los rótulos van en el idioma pedido. El enunciado JTBD
  del motor solo existe en español, así que en el documento inglés no se
  reproduce (se explica por qué) en lugar de mezclar idiomas. Las citas son
  evidencia y se dejan tal como se escribieron.
- **Fuente incrustada.** Bitstream Vera (fonts/, con su licencia): cubre
  tildes, ñ, ¿, ¡, «», — y …, así que el texto se extrae igual que se lee.
  Los bloques de código del plan usan Courier, que solo cubre Latin-1.
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
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

from core.intelligence.blueprint import build_blueprint

FUENTES = Path(__file__).resolve().parent / "fonts"
SANS = "SentraSans"
SANS_BOLD = "SentraSans-Bold"
SANS_ITALIC = "SentraSans-Italic"
MONO = "Courier"

MARGEN = 2 * cm
ESTILO_SECCION = "SentraSeccion"

TEXTOS: dict[str, dict[str, Any]] = {
    "es": {
        "doc": "Documento de oportunidad",
        "index": "Índice",
        "page": "página {n} de {total}",
        "watermark": "DATOS DE DEMOSTRACIÓN — NO REALES",
        "cover_fields": [
            "Oportunidad", "Puntuación", "Fecha de generación",
            "Fuente de los datos", "Ejecución (run_id)", "Versión de SENTRA",
        ],
        "sources": {"demo": "Demostración (corpus fabricado)", "reddit": "Reddit",
                    None: "No registrada"},
        "sections": [
            "1. Resumen ejecutivo", "2. Problema", "3. Evidencia",
            "4. Usuario objetivo y JTBD", "5. Solución propuesta",
            "6. Alcance del MVP", "7. Plan de arquitectura",
            "8. Riesgos y fallos conocidos", "9. Modelo de negocio",
            "10. Metadatos y trazabilidad",
        ],
        "no_date": "fecha no registrada",
        "no_link": "sin enlace",
        "no_quotes": "No hay citas guardadas para este problema.",
        "target_user": (
            "Participantes de {comunidades}: las comunidades donde se detectó "
            "el problema."
        ),
        "intent": "Intención dominante detectada: {intencion}.",
        "jtbd": "Trabajo por hacer, según el motor: «{jtbd}»",
        "no_jtbd": "No hay enunciado de trabajo por hacer guardado para este problema.",
        "why_fail": "Por qué fallan las soluciones actuales",
        "no_architecture": (
            "No generado: no se pidió el plan de arquitectura a Gemini en esta "
            "sesión."
        ),
        "architecture_note": (
            "Propuesta redactada por un modelo generativo (Gemini): hay que "
            "revisarla antes de ejecutarla; no es una medición."
        ),
        "risk_flags": "Banderas de riesgo marcadas por el motor: {banderas}.",
        "no_risk_flags": "El motor no marcó banderas de riesgo para este problema.",
        "undetermined": (
            "Gravedad indeterminada en {k} de {n} quejas: el clasificador no "
            "encontró evidencia suficiente y esas quejas no suman a la gravedad."
        ),
        "classifier": (
            "Las etiquetas de gravedad e intención las asigna un clasificador "
            "automático; pueden ser indeterminadas y no son una revisión humana."
        ),
        "demo_risk": (
            "Los datos de este documento son de demostración: no proceden de "
            "Reddit y no sirven para decidir."
        ),
        "unknown_source_risk": (
            "La ejecución no registró la fuente de los datos: no se puede "
            "afirmar que sean reales."
        ),
        "meta_fields": [
            "Clave del problema", "Ejecución (run_id)", "Fuente de los datos",
            "Generado", "Versión de SENTRA", "Menciones", "Comunidades",
            "Puntuación final",
            ("Factores (difusión / frecuencia / gravedad / novedad / pago)"),
            "Recuento por palabra",
        ],
        "no_count": "sin recuento guardado",
    },
    "en": {
        "doc": "Opportunity document",
        "index": "Contents",
        "page": "page {n} of {total}",
        "watermark": "DEMO DATA — NOT REAL",
        "cover_fields": [
            "Opportunity", "Score", "Generated on", "Data source",
            "Run (run_id)", "SENTRA version",
        ],
        "sources": {"demo": "Demo (fabricated corpus)", "reddit": "Reddit",
                    None: "Not recorded"},
        "sections": [
            "1. Executive summary", "2. Problem", "3. Evidence",
            "4. Target user and JTBD", "5. Proposed solution", "6. MVP scope",
            "7. Architecture plan", "8. Risks and known failures",
            "9. Business model", "10. Metadata and traceability",
        ],
        "no_date": "date not recorded",
        "no_link": "no link",
        "no_quotes": "No quotes stored for this problem.",
        "target_user": (
            "Members of {comunidades}: the communities where the problem was "
            "detected."
        ),
        "intent": "Dominant intent detected: {intencion}.",
        "jtbd": "",
        "no_jtbd": (
            "The engine only words the job to be done in Spanish, so it is not "
            "reproduced in this English document."
        ),
        "why_fail": "Why current workarounds fail",
        "no_architecture": (
            "Not generated: the architecture plan was not requested from Gemini "
            "in this session."
        ),
        "architecture_note": (
            "Proposal written by a generative model (Gemini): review it before "
            "acting on it; it is not a measurement."
        ),
        "risk_flags": "Risk flags raised by the engine: {banderas}.",
        "no_risk_flags": "The engine raised no risk flags for this problem.",
        "undetermined": (
            "Severity undetermined in {k} of {n} complaints: the classifier "
            "found no sufficient evidence and those complaints add nothing to "
            "severity."
        ),
        "classifier": (
            "Severity and intent labels are assigned by an automatic "
            "classifier; they may be undetermined and are not a human review."
        ),
        "demo_risk": (
            "The data in this document is demo data: it does not come from "
            "Reddit and is not fit for decisions."
        ),
        "unknown_source_risk": (
            "The run did not record its data source: the data cannot be "
            "claimed to be real."
        ),
        "meta_fields": [
            "Problem key", "Run (run_id)", "Data source", "Generated",
            "SENTRA version", "Mentions", "Communities", "Final score",
            "Factors (spread / frequency / severity / recency / paid)",
            "Per-keyword count",
        ],
        "no_count": "no count stored",
    },
}


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


# --- Lectura tolerante del cluster ---------------------------------------------

def _valor(cluster: Mapping[str, Any], *claves: str, defecto: Any = None) -> Any:
    """Primer valor presente entre varias grafías (camelCase o snake_case),
    mirando también dentro de `breakdown`."""
    for fuente in (cluster, cluster.get("breakdown") or {}):
        if isinstance(fuente, Mapping):
            for clave in claves:
                if fuente.get(clave) is not None:
                    return fuente[clave]
    return defecto


def _fecha(epoch: Any, textos: Mapping[str, Any]) -> str:
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError, OSError):
        return str(textos["no_date"])


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


def _evidencia(
    cluster: Mapping[str, Any], textos: Mapping[str, Any],
    estilos: Mapping[str, ParagraphStyle],
) -> list[Flowable]:
    vistas: set[str] = set()
    salida: list[Flowable] = []
    for cita in cluster.get("evidence") or []:
        if not isinstance(cita, Mapping):
            continue
        texto = str(cita.get("quote", "")).strip()
        huella = " ".join(texto.lower().split())
        if not texto or huella in vistas:
            continue
        vistas.add(huella)
        firma = " · ".join(
            parte for parte in (
                f"r/{cita.get('subreddit')}" if cita.get("subreddit") else "",
                str(cita.get("author") or ""),
                _fecha(cita.get("created_utc"), textos) if cita.get("created_utc")
                else str(textos["no_date"]),
                str(cita.get("url") or "") or str(textos["no_link"]),
            ) if parte
        )
        salida += [_p(f"«{texto}»", estilos["cita"]), _p(firma, estilos["firma"])]
    return salida or [_p(str(textos["no_quotes"]), estilos["cuerpo"])]


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
    idioma = language if language in TEXTOS else "es"
    textos = TEXTOS[idioma]
    estilos = _estilos()
    ahora = generated_at or datetime.now(timezone.utc)

    fuente = _valor(cluster, "dataSource", "data_source")
    fuente = fuente if fuente in ("demo", "reddit") else None
    etiqueta = str(_valor(cluster, "label", defecto=""))
    puntuacion = float(_valor(cluster, "finalScore", "final_score", defecto=0.0))
    run_id = str(_valor(cluster, "runId", "run_id", defecto="") or "—")
    menciones = int(_valor(cluster, "mentionCount", "mention_count", defecto=0))
    comunidades = [f"r/{s}" for s in cluster.get("subreddits") or []]
    jtbd = str(_valor(cluster, "jobStatement", "job_statement", defecto="")).strip()
    stats = _valor(cluster, "clusterStats", "cluster_stats", defecto={}) or {}

    # El PRD inglés no debe arrastrar el enunciado JTBD, que solo existe en
    # español: se genera sin él y la sección 4 explica la ausencia.
    datos_prd = dict(cluster)
    if idioma == "en":
        datos_prd.pop("jobStatement", None)
        datos_prd.pop("job_statement", None)
    prd = build_blueprint(datos_prd, idioma)
    secciones = textos["sections"]

    historia: list[Flowable] = []

    # Portada
    historia += [Spacer(1, 4 * cm), _p(etiqueta, estilos["portada"])]
    historia.append(_tabla(list(zip(textos["cover_fields"], [
        etiqueta,
        f"{puntuacion:.0f} / 100",
        ahora.strftime("%Y-%m-%d %H:%M UTC"),
        textos["sources"][fuente],
        run_id,
        version or "—",
    ], strict=True)), estilos))
    historia.append(PageBreak())

    # Índice
    indice = TableOfContents()
    indice.levelStyles = [estilos["toc"]]
    historia += [_p(textos["index"], estilos["indice"]), indice, PageBreak()]

    # 1. Resumen ejecutivo
    historia += [
        _p(secciones[0], estilos["seccion"]),
        _p(prd.source_notice, estilos["nota"]),
        _p(prd.one_liner, estilos["cuerpo"]),
        Spacer(1, 6),
        _p(prd.executive_summary, estilos["cuerpo"]),
    ]
    # 2. Problema
    historia += [_p(secciones[1], estilos["seccion"]), _p(prd.problem, estilos["cuerpo"])]
    # 3. Evidencia
    historia += [_p(secciones[2], estilos["seccion"]), *_evidencia(cluster, textos, estilos)]
    # 4. Usuario objetivo y JTBD
    historia += [
        _p(secciones[3], estilos["seccion"]),
        _p(textos["target_user"].format(comunidades=", ".join(comunidades) or "—"),
           estilos["cuerpo"]),
    ]
    intencion = str(_valor(cluster, "intentType", "intent_type", defecto="")).strip()
    if intencion:
        historia.append(_p(textos["intent"].format(intencion=intencion), estilos["cuerpo"]))
    if idioma == "es" and jtbd:
        historia.append(_p(textos["jtbd"].format(jtbd=jtbd), estilos["cuerpo"]))
    else:
        historia.append(_p(textos["no_jtbd"], estilos["cuerpo"]))
    # 5. Solución propuesta
    historia += [
        _p(secciones[4], estilos["seccion"]),
        _p(prd.solution, estilos["cuerpo"]),
        _p(textos["why_fail"], estilos["sub"]),
        _p(prd.why_existing_fail, estilos["cuerpo"]),
    ]
    # 6. Alcance del MVP
    historia.append(_p(secciones[5], estilos["seccion"]))
    for fase in prd.mvp:
        historia.append(_p(fase.name, estilos["sub"]))
        historia += [
            Paragraph(escape(item), estilos["vineta"], bulletText="•") for item in fase.items
        ]
    # 7. Plan de arquitectura
    historia.append(_p(secciones[6], estilos["seccion"]))
    if architecture and architecture.strip():
        historia += [_p(textos["architecture_note"], estilos["nota"]),
                     *_markdown(architecture, estilos)]
    else:
        historia.append(_p(textos["no_architecture"], estilos["cuerpo"]))
    # 8. Riesgos y fallos conocidos
    historia.append(_p(secciones[7], estilos["seccion"]))
    banderas = [str(b) for b in cluster.get("riskFlags") or cluster.get("risk_flags") or []]
    historia.append(_p(
        textos["risk_flags"].format(banderas=", ".join(banderas)) if banderas
        else textos["no_risk_flags"],
        estilos["cuerpo"],
    ))
    indeterminadas = stats.get("severity_undetermined") if isinstance(stats, Mapping) else None
    if indeterminadas:
        historia.append(_p(
            textos["undetermined"].format(k=int(indeterminadas), n=menciones), estilos["cuerpo"]
        ))
    historia.append(_p(textos["classifier"], estilos["cuerpo"]))
    if fuente == "demo":
        historia.append(_p(textos["demo_risk"], estilos["nota"]))
    elif fuente is None:
        historia.append(_p(textos["unknown_source_risk"], estilos["nota"]))
    # 9. Modelo de negocio
    historia += [_p(secciones[8], estilos["seccion"]), _p(prd.monetisation, estilos["cuerpo"])]
    # 10. Metadatos y trazabilidad
    factores = " / ".join(
        f"{float(_valor(cluster, clave, defecto=0.0)):.2f}"
        for clave in ("spreadFactor", "frequencyFactor", "severityFactor",
                      "recencyFactor", "paidSignalFactor")
    )
    palabras = ", ".join(
        f"{k.get('keyword')} ({k.get('count')})"
        for k in (stats.get("keywords") or [] if isinstance(stats, Mapping) else [])
        if isinstance(k, Mapping)
    ) or str(textos["no_count"])
    historia += [
        _p(secciones[9], estilos["seccion"]),
        _tabla(list(zip(textos["meta_fields"], [
            str(_valor(cluster, "clusterKey", "cluster_key", defecto="—")),
            run_id,
            textos["sources"][fuente],
            ahora.isoformat(timespec="seconds"),
            version or "—",
            str(menciones),
            str(int(_valor(cluster, "communityCount", "community_count", defecto=0))),
            f"{puntuacion:.2f}",
            factores,
            palabras,
        ], strict=True)), estilos),
    ]

    destino = io.BytesIO()
    titulo = f"SENTRA · {textos['doc']} · {etiqueta}"
    documento = _Documento(destino, titulo)
    documento.multiBuild(
        historia,
        canvasmaker=_canvas_numerado(
            titulo[:110], textos["page"], textos["watermark"] if fuente == "demo" else None
        ),
    )
    return destino.getvalue()
