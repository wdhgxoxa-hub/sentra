"""
Capa de Ingesta, Tráfico y Limpieza (Reddit Intelligence Radar)
===============================================================
Paquete central unificado que integra:
- Motor base asíncrono con SessionPool y TLS impersonation (crawlee-python).
- Inyección de cookies loid / over18 / gated opt-in (yt-dlp).
- Paginación directa cursor-based sin rate limits de API oficial (Bellingcat RPST).
- Middleware de pre-filtrado rápido con 33 expresiones de dolor B2B (reddit-painpointer).
- Deduplicación, saneamiento y generación de Markdown para LLMs (reddit-find).
- Interfoliado cronológico inverso unificado (snscrape).
"""

from .bypass import RedditBypass, RedditBypassConfig
from .client import RedditIngestionClient
from .filters import FilterResult, PainPointFilter, PAIN_POINT_KEYWORDS
from .normalizer import CleanComment, CleanPost, RedditNormalizer, UnifiedTimelineItem
from .pagination import RedditPaginator

__all__ = [
    "RedditIngestionClient",
    "RedditBypass",
    "RedditBypassConfig",
    "PainPointFilter",
    "FilterResult",
    "PAIN_POINT_KEYWORDS",
    "RedditNormalizer",
    "CleanPost",
    "CleanComment",
    "UnifiedTimelineItem",
    "RedditPaginator",
]
