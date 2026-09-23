"""
Fuente: X (API v2 de pago) — deshabilitada y sin llamadas reales
================================================================

R7 prohíbe cualquier llamada real a X en esta misión, así que la fuente
lleva dos candados: `pending_approval` (nunca entra en un escaneo, «Probar»
no sale a la red, `search` se niega) y `disabled_by_default` (sale apagada).

El código sigue la API v2 documentada: GET /2/tweets/search/recent con el
Bearer token de la app. Cada petición cuesta dinero: el coste se cuenta en
USD con un tope por escaneo. La tarifa de abajo es una estimación prudente
NO verificada; hay que ajustarla con la tarifa real antes de aprobar la
fuente. URL del original por id (x.com/i/web/status/<id>), sin usuario.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, ClassVar

from core.evidence.model import Engagement, EvidenceItem, SearchQuery

from .base import CostModel, CredentialField, ProbeResult, SourceAdapter
from .budget import SourceBudget
from .errors import SourceError, SourcePendingApproval
from .profile import term_pairs

API = "https://api.x.com/2"
MAX_RESULTS = 100
#: Estimación prudente, no verificada: se ajusta con la tarifa real antes de aprobar.
ESTIMATED_USD_PER_REQUEST = 0.01
#: Tope de gasto por escaneo.
SCAN_MAX_USD = 1.0


class XSource(SourceAdapter):
    id = "x"
    display_name = "X"
    terms_url = "https://developer.x.com/en/developer-terms/agreement-and-policy"
    commercial_use_allowed = True
    requires_credentials = True
    credential_fields = (CredentialField(name="bearer_token", env_var="RIR_X_BEARER_TOKEN"),)
    cost_model = CostModel(
        unit="usd", per_request=ESTIMATED_USD_PER_REQUEST,
        note="De pago; tarifa estimada no verificada; tope de 1 USD por escaneo",
    )
    pending_approval: ClassVar[str | None] = (
        "Deshabilitada: X es de pago y la misión prohíbe cualquier llamada real (R7).")
    disabled_by_default = True

    @classmethod
    def default_budget(cls) -> SourceBudget:
        return SourceBudget(source=cls.id, max_usd=SCAN_MAX_USD)

    def _comprobar_aprobacion(self) -> None:
        if self.pending_approval:
            raise SourcePendingApproval(self.id, self.pending_approval)

    async def probe(self) -> ProbeResult:
        try:
            self._comprobar_aprobacion()
            await self._get(f"{API}/tweets/search/recent", usd=ESTIMATED_USD_PER_REQUEST,
                            params={"query": "the", "max_results": 10},
                            headers={"Authorization": f"Bearer {self.credentials.get('bearer_token', '')}"})
        except SourceError as exc:
            return self._probe_error(exc)
        return self._probe_ok("La API de X respondió")

    async def search(self, query: SearchQuery) -> AsyncIterator[EvidenceItem]:
        self._comprobar_aprobacion()
        vistos: set[str] = set()
        for palabra, frase in term_pairs(query, limit=self.budget.max_requests):
            partes = [palabra] if palabra else []
            if frase:
                partes.append(f'"{frase}"')
            params: dict[str, Any] = {
                "query": " ".join(partes) + " -is:retweet", "max_results": MAX_RESULTS,
                "tweet.fields": "created_at,lang,public_metrics,author_id",
            }
            datos = await self._get(
                f"{API}/tweets/search/recent", usd=ESTIMATED_USD_PER_REQUEST, params=params,
                headers={"Authorization": f"Bearer {self.credentials.get('bearer_token', '')}"})
            for tuit in datos.get("data") or []:
                item = self._convertir(tuit)
                if item is not None and item.id not in vistos:
                    vistos.add(item.id)
                    yield item

    def _convertir(self, tuit: dict[str, Any]) -> EvidenceItem | None:
        nativo, texto, creado = tuit.get("id"), str(tuit.get("text") or "").strip(), tuit.get("created_at")
        if not nativo or not texto or not creado:
            return None
        metricas = tuit.get("public_metrics") or {}
        return self._item(
            nativo=str(nativo), community="X", kind="post", text=texto,
            url=f"https://x.com/i/web/status/{nativo}", author=tuit.get("author_id"),
            created_at=datetime.fromisoformat(str(creado)), language=tuit.get("lang"),
            engagement=Engagement(replies=metricas.get("reply_count"),
                                  reactions=metricas.get("like_count")),
            native={"retweets": metricas.get("retweet_count"), "quotes": metricas.get("quote_count")},
        )
