"""
Catálogo de fuentes implementadas (F2.7)
========================================

Una fuente entra aquí cuando su adaptador existe y está probado contra la
documentación oficial. Las plataformas sin API oficial para terceros (App
Store, Google Play, G2, Capterra, Trustpilot, Quora, Indie Hackers) no
entran nunca; Google Trends, tampoco mientras su API siga en alfa cerrada.
"""

from __future__ import annotations

from .base import SourceAdapter
from .bluesky import BlueskySource
from .discourse import DiscourseSource
from .github import GitHubSource
from .hackernews import HackerNewsSource
from .mastodon import MastodonSource
from .producthunt import ProductHuntSource
from .reddit import RedditSource
from .stackexchange import StackExchangeSource
from .youtube import YouTubeSource

SOURCES: tuple[type[SourceAdapter], ...] = (
    HackerNewsSource, StackExchangeSource, GitHubSource, RedditSource, BlueskySource,
    YouTubeSource, MastodonSource, DiscourseSource, ProductHuntSource,
)


def by_id(source_id: str) -> type[SourceAdapter] | None:
    return next((s for s in SOURCES if s.id == source_id), None)
