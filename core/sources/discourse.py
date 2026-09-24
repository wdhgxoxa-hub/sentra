"""
Fuente: Discourse (API pública de cada foro)
============================================

Cada foro Discourse expone su API JSON sin credenciales para lo público:
/search.json para encontrar posts (la ventana va en q como after:) y
/t/{id}/posts.json?post_ids[]=... para leer su texto completo, una petición
por tema. Los foros salen del campo `forums` de la tarjeta (obligatorio) y
de los objetivos del perfil.

- Enlace sin usuario (D-M7): https://<foro>/t/<slug>/<tema>/<n>.
- Un segundo entre peticiones: los límites de Discourse para anónimos son
  bajos y cada foro es de alguien.
- La licencia del contenido depende de cada foro: solo uso personal.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from core.evidence.model import Engagement, EvidenceItem, SearchQuery

from .base import CostModel, CredentialField, ProbeResult, SourceAdapter
from .budget import SourceBudget
from .errors import SourceCredentialsMissing, SourceError
from .hosts import domain
from .profile import term_pairs
from .text import html_to_text

#: Pausa entre peticiones al mismo foro.
MIN_INTERVAL_S = 1.0
#: Temas cuyo texto completo se lee en cada búsqueda.
TOPICS_PER_SEARCH = 5
#: Peticiones por escaneo: 1 búsqueda + TOPICS_PER_SEARCH temas por foro y
#: palabra del tema; con 25 solo cabía una palabra en tres foros.
SCAN_MAX_REQUESTS = 100


class DiscourseSource(SourceAdapter):
    id = "discourse"
    display_name = "Discourse"
    terms_url = "https://docs.discourse.org/"
    commercial_use_allowed = False
    requires_credentials = True
    credential_fields = (
        CredentialField(name="forums", env_var="RIR_DISCOURSE_FORUMS", secret=False),
    )
    cost_model = CostModel(unit="request", note="Límites de cada foro; 1 petición por segundo")

    @classmethod
    def default_budget(cls) -> SourceBudget:
        return SourceBudget(source=cls.id, max_requests=SCAN_MAX_REQUESTS)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._primera = True

    def _foros(self, query: SearchQuery | None = None) -> list[str]:
        crudos = [f for f in str(self.credentials.get("forums") or "").split(",") if f.strip()]
        crudos += list(query.targets.get(self.id, [])) if query else []
        foros: list[str] = []
        for crudo in crudos:
            dominio = domain(crudo, require_https=True)
            if dominio is None:
                raise SourceCredentialsMissing(
                    self.id, f"foro no válido (hace falta https://dominio): {crudo.strip()}")
            if dominio not in foros:
                foros.append(dominio)
        if not foros:
            raise SourceCredentialsMissing(self.id, "sin foros: añade uno en la tarjeta")
        return foros

    async def _pedir(self, url: str, params: Any = None) -> Any:
        if not self._primera:
            await self._sleep(MIN_INTERVAL_S)
        self._primera = False
        return await self._get(url, params=params)

    async def probe(self) -> ProbeResult:
        try:
            foro = self._foros()[0]
            datos = await self._pedir(f"https://{foro}/about.json")
        except SourceError as exc:
            return self._probe_error(exc)
        titulo = (datos.get("about") or {}).get("title") or foro
        return self._probe_ok(f"{foro} respondió ({titulo})")

    async def search(self, query: SearchQuery) -> AsyncIterator[EvidenceItem]:
        foros = self._foros(query)
        restantes = self.budget.max_requests - self.budget.spent_requests
        por_busqueda = 1 + TOPICS_PER_SEARCH
        # Solo el tema: los foros ya son del tema, y con la frase entre comillas
        # los tres medidos daban 0 (con el tema solo, 30–50 posts).
        pares = term_pairs(query, limit=max(1, restantes // (por_busqueda * len(foros))), solo_tema=True)
        vistos: set[str] = set()
        for palabra, frase in pares:
            partes = [palabra] if palabra else []
            if frase:
                partes.append(f'"{frase}"')
            if query.since is not None:
                partes.append(f"after:{query.since.date().isoformat()}")
            for foro in foros:
                async for item in self._buscar(foro, " ".join(partes)):
                    if item.id not in vistos:
                        vistos.add(item.id)
                        yield item

    async def _buscar(self, foro: str, q: str) -> AsyncIterator[EvidenceItem]:
        datos = await self._pedir(f"https://{foro}/search.json", params={"q": q})
        temas = {t.get("id"): t for t in datos.get("topics") or []}
        por_tema: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for post in datos.get("posts") or []:
            if post.get("topic_id") is not None and post.get("id") is not None:
                por_tema[post["topic_id"]].append(post)
        for tema_id in list(por_tema)[:TOPICS_PER_SEARCH]:
            resumen = {p["id"]: p for p in por_tema[tema_id]}
            completos = await self._pedir(
                f"https://{foro}/t/{tema_id}/posts.json",
                params=[("post_ids[]", str(i)) for i in resumen])
            for post in (completos.get("post_stream") or {}).get("posts") or []:
                item = self._convertir(foro, post, temas.get(tema_id) or {}, resumen.get(post.get("id")))
                if item is not None:
                    yield item

    def _convertir(self, foro: str, post: dict[str, Any], tema: dict[str, Any],
                   resumen: dict[str, Any] | None) -> EvidenceItem | None:
        texto = html_to_text(post.get("cooked"))
        creado, numero, tema_id = post.get("created_at"), post.get("post_number"), post.get("topic_id")
        if not texto or not creado or numero is None or tema_id is None:
            return None
        slug = post.get("topic_slug") or tema.get("slug") or "-"
        return self._item(
            nativo=f"{foro}:{post['id']}", community=foro, kind="post",
            title=tema.get("title"), text=texto, url=f"https://{foro}/t/{slug}/{tema_id}/{numero}",
            author=post.get("username"), created_at=datetime.fromisoformat(str(creado)),
            thread=f"{foro}:t{tema_id}",
            engagement=Engagement(reactions=(resumen or {}).get("like_count"),
                                  replies=post.get("reply_count")),
            native={"posts_count": tema.get("posts_count")},
        )
