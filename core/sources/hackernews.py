"""
Fuente: Hacker News (API oficial de búsqueda de Algolia)
========================================================

https://hn.algolia.com/api, sin credenciales. Límite documentado: 10.000
peticiones por hora por IP, y como mucho 1.000 resultados por consulta.
Se buscan historias (Ask HN, Show HN, enlaces) y comentarios dentro de la
ventana del perfil (`numericFilters=created_at_i>…`).

Un comentario ya trae `story_id` y `story_title`: basta para situarlo en su
hilo sin pedir el hilo entero a la API de Firebase (menos peticiones).
Los textos llegan en HTML y se limpian.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from core.evidence.model import Engagement, EvidenceItem, SearchQuery

from .base import CostModel, ProbeResult, SourceAdapter
from .errors import SourceError
from .profile import menciona_el_tema, term_pairs
from .text import html_to_text

API = "https://hn.algolia.com/api/v1"
ITEM_URL = "https://news.ycombinator.com/item?id={id}"

#: Resultados por búsqueda: uno solo pide la página más relevante de cada término.
HITS_PER_PAGE = 50
#: Hilos de empleo: perfiles y ofertas, no dolores.
_HILO_DE_EMPLEO = re.compile(r"who is hiring|who wants to be hired|seeking freelancer",
                             re.IGNORECASE)


class HackerNewsSource(SourceAdapter):
    id = "hackernews"
    display_name = "Hacker News"
    terms_url = "https://github.com/HackerNews/API"
    commercial_use_allowed = True
    requires_credentials = False
    cost_model = CostModel(unit="request", per_request=0.0,
                           note="Gratuita; 10.000 peticiones/hora por IP")

    async def probe(self) -> ProbeResult:
        try:
            datos = await self._get(f"{API}/search", params={"query": "", "hitsPerPage": 1})
        except SourceError as exc:
            return self._probe_error(exc)
        return self._probe_ok(f"API de búsqueda de HN respondió ({datos.get('nbHits', 0)} ítems)")

    async def search(self, query: SearchQuery) -> AsyncIterator[EvidenceItem]:
        restantes = self.budget.max_requests - self.budget.spent_requests
        vistos: set[str] = set()
        for palabra, frase in term_pairs(query, limit=restantes):
            params: dict[str, Any] = {
                "query": " ".join(t for t in (palabra, frase) if t),
                "tags": "(story,comment)",
                "hitsPerPage": HITS_PER_PAGE,
            }
            if query.since is not None:
                params["numericFilters"] = f"created_at_i>{int(query.since.timestamp())}"
            datos = await self._get(f"{API}/search", params=params)
            for hit in datos.get("hits") or []:
                item = self._convertir(hit)
                if item is None or item.id in vistos or not self._del_tema(hit, query):
                    continue
                vistos.add(item.id)
                yield item

    @staticmethod
    def _del_tema(hit: dict[str, Any], query: SearchQuery) -> bool:
        """Un comentario entra si no es de un hilo de empleo y habla del tema, él
        o el título de su hilo (medido: Algolia casaba palabras sueltas)."""
        if "comment" not in set(hit.get("_tags") or []) or not query.keywords:
            return True
        hilo = str(hit.get("story_title") or "")
        if _HILO_DE_EMPLEO.search(hilo):
            return False
        return menciona_el_tema(hilo, query) or menciona_el_tema(html_to_text(hit.get("comment_text")), query)

    def _convertir(self, hit: dict[str, Any]) -> EvidenceItem | None:
        nativo = str(hit.get("objectID") or "")
        etiquetas = set(hit.get("_tags") or [])
        creado = hit.get("created_at_i")
        if not nativo or creado is None:
            return None
        cuando = datetime.fromtimestamp(int(creado), UTC)
        if "comment" in etiquetas:
            texto = html_to_text(hit.get("comment_text"))
            if not texto:
                return None
            return self._item(
                nativo=nativo, community="Hacker News", kind="comment", text=texto,
                url=ITEM_URL.format(id=nativo), author=hit.get("author"), created_at=cuando,
                thread=str(hit.get("story_id") or nativo),
                native={"story_title": hit.get("story_title"), "parent_id": hit.get("parent_id")},
            )
        titulo = str(hit.get("title") or "").strip()
        texto = html_to_text(hit.get("story_text")) or titulo
        if not texto:
            return None
        comunidad = ("Ask HN" if "ask_hn" in etiquetas
                     else "Show HN" if "show_hn" in etiquetas else "Hacker News")
        return self._item(
            nativo=nativo, community=comunidad, kind="post", title=titulo or None, text=texto,
            url=ITEM_URL.format(id=nativo), author=hit.get("author"), created_at=cuando,
            engagement=Engagement(score=hit.get("points"), replies=hit.get("num_comments")),
            native={"points": hit.get("points"), "num_comments": hit.get("num_comments"),
                    "url": hit.get("url")},
        )
