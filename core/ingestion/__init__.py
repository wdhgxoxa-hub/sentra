"""
Capa de Ingesta, Tráfico y Limpieza (Reddit Intelligence Radar)
===============================================================
Paquete central unificado que integra:
- Cliente de la API OAuth de Reddit, identificado con el User-Agent de la
  app y sin suplantar a ningún navegador (AUD-014).
- Paginación directa por cursor.
- Middleware de pre-filtrado rápido con 33 expresiones de dolor B2B (reddit-painpointer).
- Deduplicación, saneamiento y generación de Markdown para LLMs (reddit-find).
- Interfoliado cronológico inverso unificado (snscrape).
"""

from .auth import RedditAuthError, RedditOAuth, load_dotenv
from .client import RedditIngestionClient
from .filters import FilterResult, PainPointFilter, PAIN_POINT_KEYWORDS
from .normalizer import CleanComment, CleanPost, RedditNormalizer, UnifiedTimelineItem
from .pagination import RedditPaginator

__all__ = [
    "RedditIngestionClient",
    "RedditOAuth",
    "RedditAuthError",
    "load_dotenv",
    "PainPointFilter",
    "FilterResult",
    "PAIN_POINT_KEYWORDS",
    "RedditNormalizer",
    "CleanPost",
    "CleanComment",
    "UnifiedTimelineItem",
    "RedditPaginator",
]
