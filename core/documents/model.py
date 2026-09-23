"""
Modelo único del documento de oportunidad (AUD-022, decisión D-H)
================================================================

El PRD que se ve en la interfaz y el PDF que se exporta eran dos documentos
distintos: la interfaz pintaba siete apartados del PRD determinista y el PDF
diez secciones con su propio contenido y su propio orden. Ahora los dos salen
de aquí: `build_document` compone las diez secciones y cada salida solo las
pinta (el PDF con ReportLab, la interfaz con React, el portapapeles como
Markdown).

Reglas del contenido (las que sostenía el PDF, AUD-008/009):

- **Nada inventado.** Cada sección sale del problema guardado (cifras,
  citas, comunidades) o del PRD determinista (`blueprint.build_blueprint`).
  Lo que no existe se dice: el plan de Gemini «No generado», una cita sin
  fecha «fecha no registrada».
- **Un solo idioma.** Los rótulos van en el idioma pedido. El enunciado JTBD
  del motor solo existe en español, así que en el documento inglés no se
  reproduce (se explica por qué). Las citas son evidencia y se dejan tal cual.
- **Procedencia a la vista.** Con datos de demostración o de fuente no
  registrada, la sección de riesgos lo dice.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from core.intelligence.blueprint import build_blueprint

#: Identificadores estables de las diez secciones, en su orden.
SECTION_IDS = (
    "summary", "problem", "evidence", "user", "solution",
    "mvp", "architecture", "risks", "business", "metadata",
)

BlockKind = Literal["paragraph", "note", "subheading", "bullets", "quote", "table", "markdown"]

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


@dataclass(frozen=True)
class Block:
    """Un bloque de contenido. Cada salida decide cómo pintar cada tipo."""

    kind: BlockKind
    text: str = ""
    items: tuple[str, ...] = ()
    signature: str = ""
    rows: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "text": self.text, "items": list(self.items),
                "signature": self.signature, "rows": [list(fila) for fila in self.rows]}


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    blocks: tuple[Block, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title,
                "blocks": [bloque.to_dict() for bloque in self.blocks]}


@dataclass(frozen=True)
class DocumentModel:
    """El documento entero: portada y diez secciones, en un idioma."""

    language: str
    label: str
    data_source: str | None
    cover: tuple[tuple[str, str], ...]
    #: De dónde salen los datos, en una frase: va antes que nada (AUD-009).
    source_notice: str = ""
    sections: tuple[Section, ...] = field(default_factory=tuple)

    def to_markdown(self) -> str:
        """El mismo documento en Markdown, para copiarlo tal como se ve.

        La primera línea declara la fuente de los datos, antes del título.
        """
        partes = [f"> {self.source_notice}" if self.source_notice else "", f"# {self.label}"]
        for seccion in self.sections:
            partes.append(f"## {seccion.title}")
            partes += [_markdown_de(bloque) for bloque in seccion.blocks]
        return "\n\n".join(p for p in partes if p) + "\n"


def _markdown_de(bloque: Block) -> str:
    if bloque.kind in ("paragraph", "markdown"):
        return bloque.text
    if bloque.kind == "note":
        return f"> {bloque.text}"
    if bloque.kind == "subheading":
        return f"### {bloque.text}"
    if bloque.kind == "bullets":
        return "\n".join(f"- {item}" for item in bloque.items)
    if bloque.kind == "quote":
        return f"> {bloque.text}\n>\n> — {bloque.signature}"
    filas = ["| | |", "|---|---|", *(f"| {k} | {v} |" for k, v in bloque.rows)]
    return "\n".join(filas)


# --- Lectura del cluster -------------------------------------------------------

def valor(cluster: Mapping[str, Any], *claves: str, defecto: Any = None) -> Any:
    """Primer valor presente entre varias grafías (camelCase o snake_case),
    mirando también dentro de `breakdown`."""
    for origen in (cluster, cluster.get("breakdown") or {}):
        if isinstance(origen, Mapping):
            for clave in claves:
                if origen.get(clave) is not None:
                    return origen[clave]
    return defecto


def fecha(epoch: Any, textos: Mapping[str, Any]) -> str:
    try:
        return datetime.fromtimestamp(float(epoch), tz=UTC).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError, OSError):
        return str(textos["no_date"])


def _evidencia(cluster: Mapping[str, Any], textos: Mapping[str, Any]) -> tuple[Block, ...]:
    vistas: set[str] = set()
    salida: list[Block] = []
    for cita in cluster.get("evidence") or []:
        if not isinstance(cita, Mapping):
            continue
        texto = str(cita.get("quote", "")).strip()
        huella = " ".join(texto.lower().split())
        if not texto or huella in vistas:
            continue
        vistas.add(huella)
        # snake_case si viene de PostgreSQL; camelCase si la reenvía Rust.
        cuando = cita.get("created_utc", cita.get("createdUtc"))
        firma = " · ".join(
            parte for parte in (
                f"r/{cita.get('subreddit')}" if cita.get("subreddit") else "",
                str(cita.get("author") or ""),
                fecha(cuando, textos) if cuando is not None else str(textos["no_date"]),
                str(cita.get("url") or "") or str(textos["no_link"]),
            ) if parte
        )
        salida.append(Block("quote", text=f"«{texto}»", signature=firma))
    return tuple(salida) or (Block("paragraph", str(textos["no_quotes"])),)


# --- Composición ------------------------------------------------------------------

def build_document(
    cluster: Mapping[str, Any],
    language: str,
    architecture: str | None = None,
    version: str = "",
    generated_at: datetime | None = None,
) -> DocumentModel:
    """Las diez secciones de una oportunidad, en `language` ("es" o "en")."""
    idioma = language if language in TEXTOS else "es"
    textos = TEXTOS[idioma]
    ahora = generated_at or datetime.now(UTC)

    fuente = valor(cluster, "dataSource", "data_source")
    fuente = fuente if fuente in ("demo", "reddit") else None
    etiqueta = str(valor(cluster, "label", defecto=""))
    puntuacion = float(valor(cluster, "finalScore", "final_score", defecto=0.0))
    run_id = str(valor(cluster, "runId", "run_id", defecto="") or "—")
    menciones = int(valor(cluster, "mentionCount", "mention_count", defecto=0))
    comunidades = [f"r/{s}" for s in cluster.get("subreddits") or []]
    jtbd = str(valor(cluster, "jobStatement", "job_statement", defecto="")).strip()
    stats = valor(cluster, "clusterStats", "cluster_stats", defecto={}) or {}
    stats = stats if isinstance(stats, Mapping) else {}

    # El PRD inglés no debe arrastrar el enunciado JTBD, que solo existe en
    # español: se genera sin él y la sección 4 explica la ausencia.
    datos_prd = dict(cluster)
    if idioma == "en":
        datos_prd.pop("jobStatement", None)
        datos_prd.pop("job_statement", None)
    prd = build_blueprint(datos_prd, idioma)

    usuario = [Block("paragraph", textos["target_user"].format(
        comunidades=", ".join(comunidades) or "—"))]
    intencion = str(valor(cluster, "intentType", "intent_type", defecto="")).strip()
    if intencion:
        usuario.append(Block("paragraph", textos["intent"].format(intencion=intencion)))
    usuario.append(Block("paragraph", textos["jtbd"].format(jtbd=jtbd)
                         if idioma == "es" and jtbd else textos["no_jtbd"]))

    mvp: list[Block] = []
    for fase in prd.mvp:
        mvp += [Block("subheading", fase.name), Block("bullets", items=tuple(fase.items))]

    arquitectura = (
        (Block("note", textos["architecture_note"]), Block("markdown", architecture))
        if architecture and architecture.strip()
        else (Block("paragraph", textos["no_architecture"]),)
    )

    banderas = [str(b) for b in cluster.get("riskFlags") or cluster.get("risk_flags") or []]
    riesgos = [Block("paragraph", textos["risk_flags"].format(banderas=", ".join(banderas))
                     if banderas else textos["no_risk_flags"])]
    indeterminadas = stats.get("severity_undetermined")
    if indeterminadas:
        riesgos.append(Block("paragraph", textos["undetermined"].format(
            k=int(indeterminadas), n=menciones)))
    riesgos.append(Block("paragraph", textos["classifier"]))
    if fuente == "demo":
        riesgos.append(Block("note", textos["demo_risk"]))
    elif fuente is None:
        riesgos.append(Block("note", textos["unknown_source_risk"]))

    factores = " / ".join(
        f"{float(valor(cluster, clave, defecto=0.0)):.2f}"
        for clave in ("spreadFactor", "frequencyFactor", "severityFactor",
                      "recencyFactor", "paidSignalFactor")
    )
    palabras = ", ".join(
        f"{k.get('keyword')} ({k.get('count')})"
        for k in stats.get("keywords") or [] if isinstance(k, Mapping)
    ) or str(textos["no_count"])
    metadatos = tuple(zip(textos["meta_fields"], [
        str(valor(cluster, "clusterKey", "cluster_key", defecto="—")),
        run_id,
        textos["sources"][fuente],
        ahora.isoformat(timespec="seconds"),
        version or "—",
        str(menciones),
        str(int(valor(cluster, "communityCount", "community_count", defecto=0))),
        f"{puntuacion:.2f}",
        factores,
        palabras,
    ], strict=True))

    contenido: tuple[tuple[Block, ...], ...] = (
        (Block("paragraph", prd.one_liner), Block("paragraph", prd.executive_summary)),
        (Block("paragraph", prd.problem),),
        _evidencia(cluster, textos),
        tuple(usuario),
        (Block("paragraph", prd.solution), Block("subheading", textos["why_fail"]),
         Block("paragraph", prd.why_existing_fail)),
        tuple(mvp),
        arquitectura,
        tuple(riesgos),
        (Block("paragraph", prd.monetisation),),
        (Block("table", rows=metadatos),),
    )

    portada = tuple(zip(textos["cover_fields"], [
        etiqueta,
        f"{puntuacion:.0f} / 100",
        ahora.strftime("%Y-%m-%d %H:%M UTC"),
        textos["sources"][fuente],
        run_id,
        version or "—",
    ], strict=True))

    return DocumentModel(
        language=idioma,
        label=etiqueta,
        data_source=fuente,
        cover=portada,
        source_notice=prd.source_notice,
        sections=tuple(
            Section(ident, titulo, bloques)
            for ident, titulo, bloques in zip(SECTION_IDS, textos["sections"], contenido,
                                              strict=True)
        ),
    )
