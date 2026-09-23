"""
Fuente: Reddit (API oficial OAuth)
==================================

El cliente de Reddit, llevado al contrato de fuentes: token con
client_credentials (autenticación básica y el User-Agent que exige Reddit:
plataforma:app:versión (by /u/usuario)) y búsqueda en oauth.reddit.com,
dentro de los subreddits del perfil o en todo Reddit.

R7: sin aprobación todavía. `pending_approval` hace que nunca entre en un
escaneo, que «Probar» no salga a la red y que `search` se niegue aunque
haya credenciales. Los términos de datos de Reddit no permiten el uso
comercial sin acuerdo: solo uso personal.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from core.evidence.model import Engagement, EvidenceItem, SearchQuery
from core.ingestion.errors import RedditUserAgentInvalid
from core.ingestion.user_agent import validar_user_agent

from .base import CostModel, CredentialField, ProbeResult, SourceAdapter
from .errors import SourceCredentialsMissing, SourceError, SourcePendingApproval
from .profile import term_pairs

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API = "https://oauth.reddit.com"
SITE = "https://www.reddit.com"
LIMIT = 100

#: Ventanas de tiempo de la búsqueda de Reddit, de menor a mayor.
_VENTANAS = (("day", 1), ("week", 7), ("month", 31), ("year", 366))


def _ventana(since: datetime | None) -> str:
    if since is None:
        return "all"
    dias = (datetime.now(UTC) - since) / timedelta(days=1)
    return next((nombre for nombre, tope in _VENTANAS if dias <= tope), "all")


class RedditSource(SourceAdapter):
    id = "reddit"
    display_name = "Reddit"
    terms_url = "https://redditinc.com/policies/data-api-terms"
    commercial_use_allowed = False
    requires_credentials = True
    credential_fields = (
        CredentialField(name="client_id", env_var="RIR_REDDIT_CLIENT_ID", secret=False),
        CredentialField(name="client_secret", env_var="RIR_REDDIT_CLIENT_SECRET"),
        CredentialField(name="user_agent", env_var="RIR_REDDIT_USER_AGENT", secret=False),
    )
    cost_model = CostModel(unit="request", note="100 peticiones/min por cliente OAuth")
    pending_approval: ClassVar[str | None] = "Pendiente de aprobación: la misión no permite llamadas reales a Reddit (R7)."

    def _comprobar_aprobacion(self) -> None:
        if self.pending_approval:
            raise SourcePendingApproval(self.id, self.pending_approval)

    def _user_agent(self) -> str:
        try:
            return validar_user_agent(self.credentials.get("user_agent"))
        except RedditUserAgentInvalid as exc:
            raise SourceCredentialsMissing(self.id, f"user_agent: {exc}") from None

    async def _token(self) -> str:
        crudo = f"{self.credentials.get('client_id', '')}:{self.credentials.get('client_secret', '')}"
        respuesta = await self._request(
            "POST", TOKEN_URL, data={"grant_type": "client_credentials"},
            headers={"Authorization": "Basic " + base64.b64encode(crudo.encode()).decode("ascii"),
                     "User-Agent": self._user_agent()})
        token = (respuesta.json() or {}).get("access_token")
        if not token:
            raise SourceCredentialsMissing(self.id, "Reddit no devolvió access_token")
        return str(token)

    async def probe(self) -> ProbeResult:
        try:
            self._comprobar_aprobacion()
            await self._token()
        except SourceError as exc:
            return self._probe_error(exc)
        return self._probe_ok("Reddit concedió un token OAuth")

    async def search(self, query: SearchQuery) -> AsyncIterator[EvidenceItem]:
        self._comprobar_aprobacion()
        cabeceras = {"Authorization": f"bearer {await self._token()}",
                     "User-Agent": self._user_agent()}
        subreddits: list[str | None] = [
            s.removeprefix("r/") for s in query.targets.get(self.id, [])] or [None]
        restantes = self.budget.max_requests - self.budget.spent_requests
        vistos: set[str] = set()
        for palabra, frase in term_pairs(query, limit=max(1, restantes // len(subreddits))):
            for sub in subreddits:
                params: dict[str, Any] = {
                    "q": " ".join(t for t in (palabra, frase) if t), "sort": "new",
                    "t": _ventana(query.since), "limit": LIMIT, "type": "link",
                }
                if sub:
                    params["restrict_sr"] = 1
                ruta = f"{API}/r/{sub}/search" if sub else f"{API}/search"
                datos = await self._get(ruta, params=params, headers=cabeceras)
                for hijo in (datos.get("data") or {}).get("children") or []:
                    item = self._convertir(hijo.get("data") or {}, query.since)
                    if item is None or item.id in vistos:
                        continue
                    vistos.add(item.id)
                    yield item

    def _convertir(self, post: dict[str, Any], since: datetime | None) -> EvidenceItem | None:
        nombre, enlace = post.get("name"), post.get("permalink")
        creado = post.get("created_utc")
        if not nombre or not enlace or creado is None:
            return None
        cuando = datetime.fromtimestamp(float(creado), UTC)
        if since is not None and cuando < since:
            return None
        titulo = str(post.get("title") or "").strip()
        texto = str(post.get("selftext") or "").strip() or titulo
        if not texto:
            return None
        return self._item(
            nativo=str(nombre), community=f"r/{post.get('subreddit') or '?'}", kind="post",
            title=titulo or None, text=texto, url=f"{SITE}{enlace}", author=post.get("author"),
            created_at=cuando,
            engagement=Engagement(score=post.get("score"), replies=post.get("num_comments")),
            native={"subreddit": post.get("subreddit")},
        )
