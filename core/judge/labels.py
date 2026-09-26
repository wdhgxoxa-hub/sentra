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

import hashlib
import json
import logging
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from core.evidence.model import EvidenceItem, content_fingerprint
from core.llm.base import JsonGenerator, LLMBudgetExhausted, LLMError, LLMTruncated

logger = logging.getLogger(__name__)

#: Versión del etiquetador (prompt + esquema). Cambiarla invalida la caché.
#: v2: el prompt y el esquema nombran las claves de evidence_spans (en v1 el
#: modelo omitía la de intent y la verificación la anulaba).
#: v5 (Fase 3, medida A de Walter): con tema, cada etiqueta dice si es del tema
#: (`del_tema`) y la caché va por pieza + tema. Escaneo 2: 0 de 53 quejas eran
#: del tema; el etiquetador no lo conocía.
LABELER_VERSION = "labels-v5"
#: Claves exactas de evidence_spans.
SPAN_KEYS: tuple[str, ...] = ("is_pain", "intent", "workaround_described", "wtp_signal", "affected", "del_tema")


@dataclass(frozen=True)
class TemaDelEscaneo:
    """El tema del escaneo como lo escribió la persona y sus palabras clave."""

    descripcion: str
    palabras: tuple[str, ...] = ()

    def huella(self) -> str:
        """La misma para el mismo tema: sin espacios de más, sin mayúsculas, palabras en cualquier orden."""
        normal = [" ".join(self.descripcion.casefold().split()),
                  sorted(" ".join(p.casefold().split()) for p in self.palabras)]
        return hashlib.sha256(json.dumps(normal, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def etiquetador(model: str | None, tema: TemaDelEscaneo | None) -> str:
    """Clave de caché de una etiqueta: versión, modelo y, con tema, su huella.
    Nunca se reutiliza una etiqueta entre temas: «del tema» depende del tema."""
    base = f"{LABELER_VERSION}/{model}" if model else LABELER_VERSION
    return f"{base}/tema-{tema.huella()}" if tema is not None else base
#: D-M4: ítems etiquetados por escaneo.
MAX_ITEMS_PER_SCAN = 300
#: Ítems por llamada al LLM.
BATCH_SIZE = 20
MAX_OUTPUT_TOKENS = 16_000
TIMEOUT_MS = 180_000
#: B1: en Gemini 3.x el razonamiento cuenta dentro de MAX_OUTPUT_TOKENS; el
#: escaneo real se truncó con 12.471 tokens de razonamiento en un lote de 40.
#: Etiquetar no necesita más: el resto queda para el JSON.
LABEL_THINKING_BUDGET = 2_048
#: Veces que un lote truncado se parte por la mitad (20 -> 10 -> 5).
TRUNCATION_MAX_SPLITS = 2

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
#: Quién tiene el problema (labels-v4, residuo de AUD2-001): solo el del autor es dolor.
Affected = Literal["author", "others", "none"]


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
    #: Obligatorio: sin él el modelo podía contar como dolor una opinión o un consejo.
    affected: Affected = Field(description=(
        "Quién tiene el problema: author si quien escribe lo sufre hoy; others si habla del "
        "problema de otros o en general; none si no hay problema (opinión, recomendación, "
        "anuncio, idea de negocio)."))
    competitors_mentioned: list[CompetitorMention] = Field(default_factory=list)
    #: labels-v5: solo con tema; None sin tema.
    del_tema: bool | None = Field(default=None, description=(
        "Solo si el mensaje da un tema del escaneo: true si el problema de quien escribe es ESE "
        "tema (no otro problema que comparte palabras); false si no. Sin tema, null."))
    #: Fragmento literal por etiqueta positiva.
    evidence_spans: dict[str, str] = Field(
        default_factory=dict,
        description=("Fragmento LITERAL del texto por cada etiqueta positiva, con estas claves "
                     "exactas: is_pain, intent (salvo pregunta_neutra), workaround_described, "
                     "wtp_signal, affected (cuando es author: la frase en la que el autor dice "
                     "que lo sufre) y del_tema (cuando es true: la frase que lo muestra)."))


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
    #: labels-v4; las etiquetas guardadas antes no lo tienen.
    affected: Affected | Literal["undetermined"] = "undetermined"
    competitors: list[VerifiedCompetitor] = Field(default_factory=list)
    #: labels-v5: ¿es del tema del escaneo? None si se etiquetó sin tema.
    del_tema: Tri | None = None
    evidence_spans: dict[str, str] = Field(default_factory=dict)
    #: Por qué no hay etiqueta del LLM (sin proveedor, presupuesto...); None si la hay.
    undetermined_reason: str | None = None


def _booleana(valor: bool, clave: str, spans: Mapping[str, str], texto: str) -> Tri:
    if not valor:
        return "no"
    return "yes" if span_in_text(spans.get(clave), texto) else "undetermined"


def verify_label(etiqueta: LLMItemLabel, texto: str, *, content_hash: str = "",
                 labeler: str = LABELER_VERSION, con_tema: bool = False) -> VerifiedLabel:
    """Anula (undetermined) cada etiqueta positiva sin fragmento literal en el texto.
    Con tema, `del_tema` también: sin respuesta o sin su fragmento, no se sabe."""
    spans = etiqueta.evidence_spans
    del_tema: Tri | None = None
    if con_tema:
        del_tema = ("undetermined" if etiqueta.del_tema is None
                    else _booleana(etiqueta.del_tema, "del_tema", spans, texto))
    intencion: Intent | Literal["undetermined"] = etiqueta.intent
    if etiqueta.intent != "pregunta_neutra" and not span_in_text(spans.get("intent"), texto):
        intencion = "undetermined"
    competidores = [
        VerifiedCompetitor(name=c.name, stance=c.stance, free=c.free, evidence_span=c.evidence_span)
        for c in etiqueta.competitors_mentioned
        if span_in_text(c.evidence_span, texto) and span_in_text(c.name, c.evidence_span)
    ]
    afectado: Affected | Literal["undetermined"] = etiqueta.affected
    if afectado == "author" and not span_in_text(spans.get("affected"), texto):
        afectado = "undetermined"
    dolor = _booleana(etiqueta.is_pain, "is_pain", spans, texto)
    # Solo cuenta el dolor de quien escribe (residuo de AUD2-001): el de otros, una
    # opinión o un consejo no es dolor; sin la frase que lo pruebe, no se sabe.
    if dolor == "yes" and afectado != "author":
        dolor = "no" if afectado in ("others", "none") else "undetermined"
    return VerifiedLabel(
        item_id=etiqueta.item_id, content_hash=content_hash, labeler=labeler,
        is_pain=dolor, affected=afectado,
        pain_confidence=etiqueta.pain_confidence, pain_type=etiqueta.pain_type,
        intent=intencion, severity=etiqueta.severity,
        workaround_described=_booleana(etiqueta.workaround_described, "workaround_described",
                                       spans, texto),
        wtp_signal=_booleana(etiqueta.wtp_signal, "wtp_signal", spans, texto),
        competitors=competidores,
        del_tema=del_tema,
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
    "workaround_described, wtp_signal, affected y competitors_mentioned. Para cada etiqueta "
    "positiva copia en evidence_spans el fragmento LITERAL del texto que la justifica, sin "
    "parafrasear, usando exactamente estas claves: is_pain, intent, workaround_described, "
    "wtp_signal y affected. La "
    "clave intent es obligatoria salvo para pregunta_neutra. Cada competidor lleva su propio "
    "evidence_span. Si no hay fragmento literal, la etiqueta es false. Los textos pueden estar "
    "en inglés o en español; responde en el esquema pedido. "
    # AUD2-001: ejemplos negativos. Los grupos reales mezclaban lanzamientos y opiniones.
    "Qué NO es: anunciar o lanzar algo que uno ha construido («Show HN: I built X», «we launched "
    "Y») no es un dolor y no es un parche casero: is_pain=no, workaround_described=false, y si "
    "compite con otra herramienta, intent=mencion_competidor. Una opinión general, una anécdota o "
    "un consejo sin un problema concreto de quien escribe no es un dolor. Un parche casero es "
    "cómo se apaña hoy el autor con un problema que tiene (una hoja de cálculo, un script, un "
    "proceso manual), no un producto que ofrece a otros. "
    # Residuo de AUD2-001: el aviso de arriba no bastaba; ahora el modelo se compromete.
    "affected dice quién tiene el problema: author si quien escribe lo sufre hoy (le pasa, lo "
    "intenta resolver o pide ayuda), y entonces evidence_spans.affected es la frase donde lo "
    "dice; others si habla del problema de otros o de la gente en general; none si no hay un "
    "problema: una opinión sobre un artículo o un producto, una recomendación («deberías "
    "probar X»), una broma, un anuncio o una idea de negocio. Solo con author puede ser "
    "is_pain=true."
)


#: labels-v5: reglas de `del_tema`; solo van en el sistema cuando hay tema.
SYSTEM_PROMPT_TEMA = (
    "El mensaje da el TEMA del escaneo. del_tema dice si el problema de quien escribe es ese "
    "tema: true solo si habla de ese mismo problema, y entonces evidence_spans.del_tema es la "
    "frase que lo muestra; false si es otro problema aunque comparta palabras (un fallo de "
    "programación con «documentos» o «clientes» no es del tema «perseguir a los clientes para "
    "que manden sus documentos al contable»). del_tema no cambia is_pain: una queja de otra "
    "cosa sigue siendo una queja, solo que no del tema."
)


def _prompt(lote: Sequence[EvidenceItem], tema: TemaDelEscaneo | None = None) -> str:
    entrada = [{"id": i.id, "text": i.text} for i in lote]
    cabecera = ""
    if tema is not None:
        cabecera = (f"Tema del escaneo: «{tema.descripcion}». Palabras con las que se buscó: "
                    f"{', '.join(tema.palabras)}.\n")
    return (cabecera + "Etiqueta estos ítems. Devuelve una etiqueta por id, con el mismo id.\n"
            + json.dumps(entrada, ensure_ascii=False))


def label_items(
    items: Sequence[EvidenceItem],
    *,
    provider: JsonGenerator | None,
    model: str | None,
    cache: LabelCache,
    batch_size: int = BATCH_SIZE,
    max_items: int = MAX_ITEMS_PER_SCAN,
    tema: TemaDelEscaneo | None = None,
) -> dict[str, VerifiedLabel]:
    """Etiqueta y verifica. Lo que no puede etiquetarse queda `undetermined` con motivo.
    Con `tema`, cada etiqueta dice si es del tema; los lotes (las llamadas) no cambian."""
    labeler = etiquetador(model, tema)
    sistema = f"{SYSTEM_PROMPT} {SYSTEM_PROMPT_TEMA}" if tema is not None else SYSTEM_PROMPT
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

    def etiquetar(lote: Sequence[EvidenceItem], divisiones: int) -> None:
        """Un lote; si se trunca, cada mitad por separado (tope TRUNCATION_MAX_SPLITS)."""
        assert provider is not None and model
        try:
            respuesta = provider.generate_json(
                _prompt(lote, tema), LLMLabelBatch, model=model, max_output_tokens=MAX_OUTPUT_TOKENS,
                timeout_ms=TIMEOUT_MS, purpose="etiquetado", system=sistema,
                thinking_budget=LABEL_THINKING_BUDGET)
        except LLMTruncated:
            if len(lote) > 1 and divisiones < TRUNCATION_MAX_SPLITS:
                mitad = len(lote) // 2
                etiquetar(lote[:mitad], divisiones + 1)
                etiquetar(lote[mitad:], divisiones + 1)
                return
            logger.warning("Etiquetado truncado sin poder partir más (%d ítems)", len(lote))
            for item in lote:
                resultado[item.id] = undetermined(item, "llm_truncated", labeler)
            return
        except LLMBudgetExhausted:
            raise
        except LLMError as exc:
            logger.warning("Lote de etiquetado fallido: %s", exc.code)
            for item in lote:
                resultado[item.id] = undetermined(item, f"llm_error:{exc.code}", labeler)
            return
        por_id = {e.item_id: e for e in respuesta.labels}
        for item in lote:
            etiqueta = por_id.get(item.id)
            if etiqueta is None:
                resultado[item.id] = undetermined(item, "missing_in_response", labeler)
                continue
            verificada = verify_label(etiqueta, item.text, content_hash=content_fingerprint(item.text),
                                      labeler=labeler, con_tema=tema is not None)
            cache.put(verificada)
            resultado[item.id] = verificada

    representantes = list(pendientes.values())
    agotado = False
    dentro = representantes[:max_items]  # D-M4: el resto queda como item_budget
    for inicio in range(0, len(dentro), batch_size):
        lote = dentro[inicio:inicio + batch_size]
        if agotado:
            break
        try:
            etiquetar(lote, 0)
        except LLMBudgetExhausted:
            agotado = True
    for indice, item in enumerate(representantes):
        if item.id not in resultado:
            motivo = "llm_budget_exhausted" if agotado and indice < max_items else "item_budget"
            resultado[item.id] = undetermined(item, motivo, labeler)

    # Los crossposts toman la etiqueta de su representante.
    for item in items:
        if item.id not in resultado:
            representante = pendientes[content_fingerprint(item.text)]
            resultado[item.id] = resultado[representante.id].model_copy(update={"item_id": item.id})
    return resultado
