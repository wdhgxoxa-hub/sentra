"""
Juez, etapa 1: etiquetado de cada ítem por el LLM
=================================================

El LLM etiqueta; no juzga. Por cada ítem devuelve is_pain (con confianza),
pain_type, intent, severity, workaround_described, wtp_signal,
competitors_mentioned y, OBLIGATORIAMENTE, el fragmento literal del texto
(`evidence_span`) que justifica cada etiqueta positiva.

Anti-alucinación: si el fragmento no aparece literalmente en el texto del
ítem, esa etiqueta se anula y queda `undetermined`. «Literal» tolera solo
diferencias de espacios, mayúsculas y forma Unicode; nunca otras palabras.
"""

from __future__ import annotations

import json
import logging
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from core.evidence.model import EvidenceItem, content_fingerprint
from core.llm.base import LLMBudgetExhausted, LLMError, LLMProvider

logger = logging.getLogger(__name__)

#: Versión del etiquetador (prompt + esquema). Cambiarla invalida la caché.
LABELER_VERSION = "labels-v1"
#: D-M4: ítems etiquetados por escaneo.
MAX_ITEMS_PER_SCAN = 300
#: Ítems por llamada al LLM.
BATCH_SIZE = 20
MAX_OUTPUT_TOKENS = 16_000
TIMEOUT_MS = 180_000

#: Intenciones posibles (F3.2).
Intent = Literal["busca_herramienta", "queja", "parche_casero", "dispuesto_a_pagar",
                 "mencion_competidor", "pregunta_neutra"]
INTENTS: tuple[str, ...] = ("busca_herramienta", "queja", "parche_casero", "dispuesto_a_pagar",
                            "mencion_competidor", "pregunta_neutra")
#: Cómo habla el ítem de un competidor.
Stance = Literal["queja", "satisfecho", "neutral"]
STANCES: tuple[str, ...] = ("queja", "satisfecho", "neutral")
#: Valor verificado de una etiqueta.
Tri = Literal["yes", "no", "undetermined"]


def _normalizar(texto: str) -> str:
    return " ".join(unicodedata.normalize("NFC", texto).casefold().split())


def span_in_text(span: str | None, text: str) -> bool:
    """¿Aparece el fragmento literalmente en el texto? Vacío = no respalda nada."""
    fragmento = _normalizar(span or "")
    return bool(fragmento) and fragmento in _normalizar(text)


class CompetitorMention(BaseModel):
    name: str
    stance: Stance
    #: ¿Lo describe el texto como gratuito? None si no lo dice.
    free: bool | None = None
    evidence_span: str = ""


class LLMItemLabel(BaseModel):
    """Lo que devuelve el LLM por ítem (sin verificar)."""

    item_id: str
    is_pain: bool
    pain_confidence: float = Field(ge=0.0, le=1.0)
    pain_type: str | None = None
    intent: Intent
    severity: Literal["baja", "media", "alta"] | None = None
    workaround_described: bool
    wtp_signal: bool
    competitors_mentioned: list[CompetitorMention] = Field(default_factory=list)
    #: Fragmento literal por etiqueta positiva: is_pain, intent, workaround_described, wtp_signal.
    evidence_spans: dict[str, str] = Field(default_factory=dict)


class LLMLabelBatch(BaseModel):
    labels: list[LLMItemLabel]


class VerifiedCompetitor(BaseModel):
    name: str
    stance: Stance
    free: bool | None = None
    evidence_span: str


class VerifiedLabel(BaseModel):
    """Etiqueta tras la verificación: lo no respaldado literalmente es `undetermined`."""

    item_id: str
    content_hash: str
    labeler: str
    is_pain: Tri
    pain_confidence: float | None = None
    pain_type: str | None = None
    intent: Intent | Literal["undetermined"]
    severity: Literal["baja", "media", "alta"] | None = None
    workaround_described: Tri
    wtp_signal: Tri
    competitors: list[VerifiedCompetitor] = Field(default_factory=list)
    evidence_spans: dict[str, str] = Field(default_factory=dict)
    #: Por qué no hay etiqueta del LLM (sin proveedor, presupuesto...); None si la hay.
    undetermined_reason: str | None = None


def _booleana(valor: bool, clave: str, spans: Mapping[str, str], texto: str) -> Tri:
    if not valor:
        return "no"
    return "yes" if span_in_text(spans.get(clave), texto) else "undetermined"


def verify_label(etiqueta: LLMItemLabel, texto: str, *, content_hash: str = "",
                 labeler: str = LABELER_VERSION) -> VerifiedLabel:
    """Anula (undetermined) cada etiqueta positiva sin fragmento literal en el texto."""
    spans = etiqueta.evidence_spans
    intencion: Intent | Literal["undetermined"] = etiqueta.intent
    if etiqueta.intent != "pregunta_neutra" and not span_in_text(spans.get("intent"), texto):
        intencion = "undetermined"
    competidores = [
        VerifiedCompetitor(name=c.name, stance=c.stance, free=c.free, evidence_span=c.evidence_span)
        for c in etiqueta.competitors_mentioned
        if span_in_text(c.evidence_span, texto) and span_in_text(c.name, c.evidence_span)
    ]
    return VerifiedLabel(
        item_id=etiqueta.item_id, content_hash=content_hash, labeler=labeler,
        is_pain=_booleana(etiqueta.is_pain, "is_pain", spans, texto),
        pain_confidence=etiqueta.pain_confidence, pain_type=etiqueta.pain_type,
        intent=intencion, severity=etiqueta.severity,
        workaround_described=_booleana(etiqueta.workaround_described, "workaround_described",
                                       spans, texto),
        wtp_signal=_booleana(etiqueta.wtp_signal, "wtp_signal", spans, texto),
        competitors=competidores,
        evidence_spans={k: v for k, v in spans.items() if span_in_text(v, texto)},
    )


def undetermined(item: EvidenceItem, motivo: str, labeler: str = LABELER_VERSION) -> VerifiedLabel:
    """Sin etiqueta del LLM: todo `undetermined`, con el motivo. Nunca una heurística."""
    return VerifiedLabel(item_id=item.id, content_hash=content_fingerprint(item.text),
                         labeler=labeler, is_pain="undetermined", intent="undetermined",
                         workaround_described="undetermined", wtp_signal="undetermined",
                         undetermined_reason=motivo)


class LabelCache(Protocol):
    """Etiquetas por (hash de contenido, etiquetador): el mismo texto no se paga dos veces."""

    def get(self, content_hash: str, labeler: str) -> VerifiedLabel | None: ...

    def put(self, label: VerifiedLabel) -> None: ...


class InMemoryLabelCache:
    def __init__(self) -> None:
        self._etiquetas: dict[tuple[str, str], VerifiedLabel] = {}

    def get(self, content_hash: str, labeler: str) -> VerifiedLabel | None:
        return self._etiquetas.get((content_hash, labeler))

    def put(self, label: VerifiedLabel) -> None:
        self._etiquetas[(label.content_hash, label.labeler)] = label


SYSTEM_PROMPT = (
    "Eres un etiquetador de evidencia de mercado. No juzgas ni recomiendas: solo etiquetas. "
    "Para cada ítem devuelve is_pain, pain_confidence, pain_type, intent, severity, "
    "workaround_described, wtp_signal y competitors_mentioned. Para cada etiqueta positiva "
    "copia en evidence_spans el fragmento LITERAL del texto que la justifica, sin parafrasear; "
    "si no hay fragmento literal, la etiqueta es false. Los textos pueden estar en inglés o en "
    "español; responde en el esquema pedido."
)


def _prompt(lote: Sequence[EvidenceItem]) -> str:
    entrada = [{"id": i.id, "text": i.text} for i in lote]
    return ("Etiqueta estos ítems. Devuelve una etiqueta por id, con el mismo id.\n"
            + json.dumps(entrada, ensure_ascii=False))


def label_items(
    items: Sequence[EvidenceItem],
    *,
    provider: LLMProvider | None,
    model: str | None,
    cache: LabelCache,
    batch_size: int = BATCH_SIZE,
    max_items: int = MAX_ITEMS_PER_SCAN,
) -> dict[str, VerifiedLabel]:
    """Etiqueta y verifica. Lo que no puede etiquetarse queda `undetermined` con motivo."""
    labeler = f"{LABELER_VERSION}/{model}" if model else LABELER_VERSION
    resultado: dict[str, VerifiedLabel] = {}
    if provider is None or not model:
        return {i.id: undetermined(i, "no_provider", labeler) for i in items}

    # Un solo representante por texto: los crossposts comparten etiqueta.
    pendientes: dict[str, EvidenceItem] = {}
    for item in items:
        huella = content_fingerprint(item.text)
        guardada = cache.get(huella, labeler)
        if guardada is not None:
            resultado[item.id] = guardada.model_copy(update={"item_id": item.id})
        elif huella not in pendientes:
            pendientes[huella] = item

    representantes = list(pendientes.values())
    fuera = representantes[max_items:]
    agotado: str | None = None
    for inicio in range(0, min(len(representantes), max_items), batch_size):
        lote = representantes[inicio:inicio + batch_size]
        if agotado:
            fuera += lote
            continue
        try:
            respuesta = provider.generate_json(
                _prompt(lote), LLMLabelBatch, model=model, max_output_tokens=MAX_OUTPUT_TOKENS,
                timeout_ms=TIMEOUT_MS, system=SYSTEM_PROMPT)
        except LLMBudgetExhausted:
            agotado = "llm_budget_exhausted"
            fuera += lote
            continue
        except LLMError as exc:
            logger.warning("Lote de etiquetado fallido: %s", exc.code)
            for item in lote:
                resultado[item.id] = undetermined(item, f"llm_error:{exc.code}", labeler)
            continue
        por_id = {e.item_id: e for e in respuesta.labels}
        for item in lote:
            etiqueta = por_id.get(item.id)
            if etiqueta is None:
                resultado[item.id] = undetermined(item, "missing_in_response", labeler)
                continue
            verificada = verify_label(etiqueta, item.text,
                                      content_hash=content_fingerprint(item.text), labeler=labeler)
            cache.put(verificada)
            resultado[item.id] = verificada

    for item in fuera:
        motivo = agotado if agotado and item in representantes[:max_items] else "item_budget"
        resultado[item.id] = undetermined(item, motivo, labeler)

    # Los crossposts toman la etiqueta de su representante.
    for item in items:
        if item.id not in resultado:
            representante = pendientes[content_fingerprint(item.text)]
            resultado[item.id] = resultado[representante.id].model_copy(update={"item_id": item.id})
    return resultado
