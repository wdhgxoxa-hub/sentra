"""
Fuente: Product Hunt (API GraphQL v2 oficial)
=============================================

La API no busca por texto libre: topics(query:) encuentra los temas que
casan con cada palabra clave del perfil y posts(topic:, postedAfter:) trae
sus productos con los comentarios. El producto es la oferta que ya existe
(el hueco se ve en lo que le falta); los comentarios, lo que la gente pide.

- Token de desarrollador (RIR_PRODUCTHUNT_TOKEN) como Bearer.
- Errores GraphQL que llegan con HTTP 200 en `errors`; cuota por complejidad
  en X-Rate-Limit-* (el reinicio, en segundos).
- Los usuarios ajenos llegan ocultos con id "0": ese autor no se cuenta
  (hashearlo juntaría a todos en uno e inflaría los autores distintos).
- Términos: sin uso comercial sin permiso de Product Hunt.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx

from core.evidence.model import Engagement, EvidenceItem, SearchQuery

from .base import CostModel, CredentialField, ProbeResult, SourceAdapter, _numero
from .errors import SourceAuthFailed, SourceError, SourceRateLimited

API = "https://api.producthunt.com/v2/api/graphql"
TOPICS_PER_KEYWORD = 3
POSTS_PER_TOPIC = 20
COMMENTS_PER_POST = 20
#: Usuario oculto por la API.
HIDDEN_USER_ID = "0"

_TEMAS = """query Temas($query: String!, $first: Int!) {
  topics(query: $query, first: $first) { edges { node { id slug name } } }
}"""

_POSTS = """query Posts($topic: String, $postedAfter: DateTime, $first: Int!, $comments: Int!) {
  posts(topic: $topic, postedAfter: $postedAfter, first: $first, order: NEWEST) {
    edges { node {
      id name tagline description url createdAt votesCount commentsCount
      comments(first: $comments) { edges { node { id body createdAt votesCount url user { id } } } }
    } }
  }
}"""

_SONDA = "query Sonda { topics(first: 1) { edges { node { id } } } }"


class ProductHuntSource(SourceAdapter):
    id = "producthunt"
    display_name = "Product Hunt"
    terms_url = "https://api.producthunt.com/v2/docs"
    commercial_use_allowed = False
    requires_credentials = True
    credential_fields = (CredentialField(name="token", env_var="RIR_PRODUCTHUNT_TOKEN"),)
    cost_model = CostModel(unit="request", note="Cuota por complejidad: 6.250 puntos cada 15 min")

    async def _graphql(self, consulta: str, variables: dict[str, Any] | None = None) -> Any:
        respuesta = await self._request(
            "POST", API, json={"query": consulta, "variables": variables or {}},
            headers={"Authorization": f"Bearer {self.credentials.get('token', '')}"})
        datos = respuesta.json() or {}
        if errores := datos.get("errors"):
            raise self._error_graphql(errores)
        return datos.get("data") or {}

    def _error_graphql(self, errores: list[Any]) -> SourceError:
        nombres = {str(e.get("error") or e.get("message") or "") for e in errores if isinstance(e, dict)}
        detalle = ", ".join(sorted(nombres)) or "error GraphQL"
        if nombres & {"invalid_oauth_token", "unauthorized_oauth", "unauthorized"}:
            return SourceAuthFailed(self.id, detalle)
        if "rate_limit_reached" in nombres:
            return SourceRateLimited(self.id, detalle, retry_after=self.quota.reset_epoch
                                     and max(self.quota.reset_epoch - time.time(), 0.0))
        return SourceError(self.id, detalle)

    def _leer_cuota(self, cabeceras: httpx.Headers) -> None:
        super()._leer_cuota(cabeceras)
        if (limite := _numero(cabeceras.get("X-Rate-Limit-Limit"))) is not None:
            self.quota.limit = int(limite)
        if (restante := _numero(cabeceras.get("X-Rate-Limit-Remaining"))) is not None:
            self.quota.remaining = int(restante)
        if (segundos := _numero(cabeceras.get("X-Rate-Limit-Reset"))) is not None:
            self.quota.reset_epoch = time.time() + segundos

    async def probe(self) -> ProbeResult:
        try:
            await self._graphql(_SONDA)
        except SourceError as exc:
            return self._probe_error(exc)
        return self._probe_ok("La API de Product Hunt respondió con el token")

    async def search(self, query: SearchQuery) -> AsyncIterator[EvidenceItem]:
        despues = (query.since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                   if query.since is not None else None)
        vistos: set[str] = set()
        temas: list[tuple[str | None, str]] = []
        for palabra in query.keywords:
            datos = await self._graphql(_TEMAS, {"query": palabra, "first": TOPICS_PER_KEYWORD})
            for arista in (datos.get("topics") or {}).get("edges") or []:
                nodo = arista.get("node") or {}
                if nodo.get("slug") and (nodo["slug"], nodo.get("name")) not in temas:
                    temas.append((nodo["slug"], str(nodo.get("name") or nodo["slug"])))
        if query.discovery:
            temas.append((None, "Novedades"))
        for slug, nombre in temas:
            datos = await self._graphql(_POSTS, {"topic": slug, "postedAfter": despues,
                                                 "first": POSTS_PER_TOPIC,
                                                 "comments": COMMENTS_PER_POST})
            for arista in (datos.get("posts") or {}).get("edges") or []:
                for item in self._convertir(arista.get("node") or {}, nombre):
                    if item.id not in vistos:
                        vistos.add(item.id)
                        yield item

    def _convertir(self, post: dict[str, Any], tema: str) -> list[EvidenceItem]:
        if not post.get("id") or not post.get("url") or not post.get("createdAt"):
            return []
        comunidad = f"Product Hunt · {tema}"
        texto = "\n\n".join(t for t in (str(post.get("tagline") or "").strip(),
                                        str(post.get("description") or "").strip()) if t)
        items = []
        if texto:
            items.append(self._item(
                nativo=str(post["id"]), community=comunidad, kind="product",
                title=post.get("name"), text=texto, url=str(post["url"]), author=None,
                created_at=datetime.fromisoformat(str(post["createdAt"])),
                engagement=Engagement(score=post.get("votesCount"),
                                      replies=post.get("commentsCount")),
            ))
        for arista in (post.get("comments") or {}).get("edges") or []:
            nodo = arista.get("node") or {}
            cuerpo = str(nodo.get("body") or "").strip()
            if not nodo.get("id") or not cuerpo or not nodo.get("createdAt"):
                continue
            usuario = str((nodo.get("user") or {}).get("id") or "")
            items.append(self._item(
                nativo=f"c{nodo['id']}", community=comunidad, kind="comment", text=cuerpo,
                url=str(nodo.get("url") or post["url"]),
                author=usuario if usuario and usuario != HIDDEN_USER_ID else None,
                created_at=datetime.fromisoformat(str(nodo["createdAt"])),
                thread=str(post["id"]), engagement=Engagement(score=nodo.get("votesCount")),
            ))
        return items
