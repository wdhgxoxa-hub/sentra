"""
Juez, etapa 0: filtro de calidad determinista
=============================================

Descarta lo que no es evidencia y registra por qué: texto demasiado corto,
idioma no soportado, spam de enlaces, afiliados y bots. La autopromoción
(«I built X», «he creado…») no se descarta: no cuenta como dolor, pero se
conserva marcada como señal de competencia.

Reglas en orden; la primera que casa da el motivo.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from core.evidence.model import EvidenceItem

#: Por debajo, no hay dolor que leer («+1», «same here»).
MIN_CHARS = 20
MIN_WORDS = 4
#: Idiomas que el etiquetado y el conjunto dorado cubren.
SUPPORTED_LANGUAGES = frozenset({"en", "es"})
#: A partir de aquí, un texto es un escaparate de enlaces.
MAX_LINKS = 3

_ENLACE = re.compile(r"https?://\S+", re.IGNORECASE)
_AFILIADO = re.compile(
    r"[?&](ref|aff|affiliate|via|coupon)=|\baffiliate link\b|\bpromo code\b|\bdiscount code\b"
    r"|\buse my (code|link)\b|\bc[oó]digo de descuento\b|\bc[oó]digo promocional\b"
    r"|\benlace de (afiliado|referido)\b",
    re.IGNORECASE)
_BOT = re.compile(
    r"\bi am a bot\b|\bi'm a bot\b|\bthis action was performed automatically\b"
    r"|\bbeep boop\b|\bsoy un bot\b|\bmensaje autom[aá]tico\b",
    re.IGNORECASE)
_AUTOPROMOCION = re.compile(
    r"\b(i|we) (built|made|created|launched|released|shipped)\b|\bcheck out my\b"
    r"|\bmy (new )?(app|tool|saas|startup|product)\b"
    r"|\bhe (creado|construido|hecho|lanzado)\b|\bhemos (creado|construido|lanzado)\b"
    r"|\bconstru[ií]\b|\blanc[eé]\b|\bmi (nueva )?(app|herramienta|startup)\b",
    re.IGNORECASE)
#: Anuncio «problema → solución» (escaneo de impagos, Bluesky): «X a mano es un
#: rollo. The fix: …», o «X used to … Now …» describiendo una automatización.
#: Una queja con antes y ahora («used to pay in 30 days. Now 90») no lo es.
_ANUNCIO_SOLUCION = re.compile(r"\b(the fix|la soluci[oó]n)\s*:", re.IGNORECASE)
_ANTES_AHORA = re.compile(r"\bused to\b[^.?!]{0,80}[.?!]\s+now\b|\bantes\b[^.?!]{0,80}[.?!]\s+ahora\b",
                          re.IGNORECASE)
_AUTOMATIZA = re.compile(r"automat|autom[aá]tic|scheduled|programad|on (its|their) own|by itself|"
                         r"themselves|without (me|you)\b", re.IGNORECASE)


def es_autopromocion(texto: str) -> bool:
    """Quien habla vende lo suyo: competencia, no dolor."""
    return bool(_AUTOPROMOCION.search(texto) or _ANUNCIO_SOLUCION.search(texto)
                or (_ANTES_AHORA.search(texto) and _AUTOMATIZA.search(texto)))


@dataclass(frozen=True)
class QualityVerdict:
    item_id: str
    keep: bool
    #: Motivo del descarte, o `self_promotion` si se conserva como competencia.
    reason: str | None
    competition_signal: bool


@dataclass
class QualityResult:
    kept: list[EvidenceItem] = field(default_factory=list)
    discarded: list[QualityVerdict] = field(default_factory=list)
    #: Conservados como señal de competencia (no cuentan como dolor).
    competition: list[QualityVerdict] = field(default_factory=list)


def _descartar(item: EvidenceItem, motivo: str) -> QualityVerdict:
    return QualityVerdict(item.id, False, motivo, False)


def judge_quality(item: EvidenceItem) -> QualityVerdict:
    texto = item.text.strip()
    sin_enlaces = _ENLACE.sub("", texto)
    if len(texto) < MIN_CHARS or len(sin_enlaces.split()) < MIN_WORDS:
        return _descartar(item, "too_short")
    idioma = (item.language or "").split("-")[0].lower()
    if idioma and idioma not in SUPPORTED_LANGUAGES:
        return _descartar(item, "unsupported_language")
    if _AFILIADO.search(texto):
        return _descartar(item, "affiliate")
    enlaces = len(_ENLACE.findall(texto))
    if enlaces >= MAX_LINKS or (enlaces and len(sin_enlaces.strip()) < MIN_CHARS):
        return _descartar(item, "spam")
    if _BOT.search(texto):
        return _descartar(item, "bot")
    if es_autopromocion(texto):
        return QualityVerdict(item.id, True, "self_promotion", True)
    return QualityVerdict(item.id, True, None, False)


def filter_quality(items: Sequence[EvidenceItem]) -> QualityResult:
    resultado = QualityResult()
    for item in items:
        veredicto = judge_quality(item)
        if not veredicto.keep:
            resultado.discarded.append(veredicto)
            continue
        resultado.kept.append(item)
        if veredicto.competition_signal:
            resultado.competition.append(veredicto)
    return resultado
