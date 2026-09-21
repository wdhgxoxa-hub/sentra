"""
Middleware de Filtrado Rápido y Detección Léxica de Dolor
=========================================================
Integra:
1. Las 33 expresiones exactas de frustración B2B de reddit-painpointer (app/lib/ai.ts).
2. Detección de spam de afiliados y contenido de noticias de pain-miner (painminer/analysis.py).
3. Detección y descarte de respuestas automáticas de bots / AutoModerator.

Este middleware actúa como primera barrera de corte de alto rendimiento (regex compiladas),
evitando procesar texto irrelevante en etapas más costosas (LLM o bases vectoriales).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# 33 palabras clave y frases curadas de dolor y frustración B2B de reddit-painpointer
PAIN_POINT_KEYWORDS: List[str] = [
    "spending hours every",
    "hate manually doing",
    "tedious process",
    "painful workflow",
    "waste so much time",
    "I'd pay for",
    "wish there was a tool",
    "need automation for",
    "tired of doing",
    "kills my productivity",
    "bottleneck in my",
    "repetitive task",
    "slow me down",
    "takes forever to",
    "frustrated with",
    "anyone else struggling with",
    "better way to",
    "how do you all handle",
    "exhausted from",
    "can't keep up with",
    "drowning in",
    "overwhelmed by",
    "hourly rate",
    "manual",
    "client work",
    "invoice",
    "time consuming",
    "takes hours",
    "manually",
    "every day",
    "paying for",
    "but still",
    "automate",
]

# Patrones de spam de afiliados y enlaces de referidos extraídos de pain-miner
AFFILIATE_REGEX = re.compile(
    r"\b(?:affiliate|referral|ref=|utm_[a-z_]+|promo\s*code|discount\s*code|coupon)\b",
    re.IGNORECASE
)

# Patrones de anuncios, lanzamientos corporativos o noticias de prensa
EVENT_DRIVEN_REGEX = re.compile(
    r"\b(?:breaking\s*news|press\s*release|announced|announcement|we\s*just\s*launched|product\s*hunt)\b",
    re.IGNORECASE
)

# Identificadores comunes de bots y automoderadores de Reddit
BOT_AUTHORS = {
    "automoderator",
    "bot",
    "reddit",
    "remindmebot",
    "savevideobot",
    "qualityvote",
    "moderator",
}

BOT_TEXT_REGEX = re.compile(
    r"(?:i\s*am\s*a\s*bot|action\s*was\s*performed\s*automatically|contact\s*the\s*moderators\s*of\s*this\s*subreddit)",
    re.IGNORECASE
)


@dataclass
class FilterResult:
    """Resultado de la evaluación de filtrado rápido."""
    passed: bool
    is_pain_signal: bool
    matched_keywords: List[str] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)


class PainPointFilter:
    """
    Motor de filtrado léxico rápido para pre-selección de publicaciones y comentarios.
    """

    def __init__(
        self,
        keywords: Optional[Sequence[str]] = None,
        discard_bots: bool = True,
        discard_affiliates: bool = True,
        discard_news: bool = False,
    ) -> None:
        self.keywords = list(keywords) if keywords is not None else PAIN_POINT_KEYWORDS
        self.discard_bots = discard_bots
        self.discard_affiliates = discard_affiliates
        self.discard_news = discard_news

        # Compilar patrones regex para coincidencia ultra-rápida
        escaped_kws = [re.escape(k) for k in self.keywords]
        self._pain_pattern = re.compile(
            r"\b(?:" + "|".join(escaped_kws) + r")\b",
            re.IGNORECASE
        )

    def match_keywords(self, text: str) -> List[str]:
        """Encuentra todas las palabras clave de dolor presentes en el texto."""
        if not text:
            return []
        matches = self._pain_pattern.findall(text)
        # Normalizar a minúsculas y deduplicar manteniendo orden
        seen = set()
        result = []
        for m in matches:
            m_lower = m.lower()
            if m_lower not in seen:
                seen.add(m_lower)
                result.append(m_lower)
        return result

    def contains_pain_signal(self, text: str) -> bool:
        """Determina rápidamente si el texto contiene al menos una señal léxica de dolor."""
        if not text:
            return False
        return bool(self._pain_pattern.search(text))

    def is_spam_or_affiliate(self, text: str) -> bool:
        """Verifica si el texto contiene patrones de spam de afiliados o códigos promocionales."""
        if not text:
            return False
        return bool(AFFILIATE_REGEX.search(text))

    def is_bot_content(self, author: str, text: str) -> bool:
        """Detecta si el autor o el cuerpo del mensaje corresponde a un bot o AutoMod."""
        clean_author = (author or "").strip().lower()
        if clean_author in BOT_AUTHORS or clean_author.endswith("bot"):
            return True
        if text and BOT_TEXT_REGEX.search(text):
            return True
        return False

    def evaluate(
        self,
        text: str,
        author: str = "",
        require_pain_match: bool = True
    ) -> FilterResult:
        """
        Evalúa un ítem (post o comentario) contra la batería de filtros heurísticos.

        :param text: Contenido de texto (título + cuerpo o cuerpo del comentario).
        :param author: Nombre del usuario de Reddit.
        :param require_pain_match: Si es True, exige al menos una palabra clave de dolor para pasar.
        :return: FilterResult con veredicto, razones y palabras coincidentes.
        """
        rejection_reasons = []
        risk_flags = []

        # 1. Detección de bots
        if self.discard_bots and self.is_bot_content(author, text):
            rejection_reasons.append("bot_or_automod_content")

        # 2. Detección de spam / afiliados
        if self.is_spam_or_affiliate(text):
            risk_flags.append("affiliate_or_promo_spam")
            if self.discard_affiliates:
                rejection_reasons.append("contains_affiliate_links")

        # 3. Detección de notas de prensa / eventos
        if EVENT_DRIVEN_REGEX.search(text or ""):
            risk_flags.append("news_or_launch_announcement")
            if self.discard_news:
                rejection_reasons.append("press_release_event")

        # 4. Señales de dolor
        matched = self.match_keywords(text)
        is_pain = len(matched) > 0

        if require_pain_match and not is_pain:
            rejection_reasons.append("no_pain_keywords_found")

        passed = len(rejection_reasons) == 0

        return FilterResult(
            passed=passed,
            is_pain_signal=is_pain,
            matched_keywords=matched,
            rejection_reasons=rejection_reasons,
            risk_flags=risk_flags
        )
