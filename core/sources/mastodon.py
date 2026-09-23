"""
Fuente: Mastodon (API oficial de la instancia)
==============================================

Búsqueda de estados con GET /api/v2/search?type=statuses en la instancia
del usuario, con su token (permisos read:search y read:statuses). La
búsqueda de texto completo solo alcanza lo que la instancia indexa: estados
cuyos autores aceptaron aparecer en búsquedas, y los que ya conoce.

- Solo estados públicos: lo no listado o privado no se guarda.
- D-M7 (R5 frente a R9): la URL guardada es la de la API por id de estado,
  https://<instancia>/api/v1/statuses/<id>, que no lleva @usuario; la
  comunidad es el dominio del servidor del autor, sin su nombre. El autor,
  solo como hash (instancia + id de cuenta).
- Cuota: 300 peticiones cada 5 minutos por cuenta; X-RateLimit-Reset llega
  en ISO 8601.
- Los términos dependen de cada instancia y no se han verificado: solo uso
  personal.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx

from core.evidence.model import Engagement, EvidenceItem, SearchQuery

from .base import CostModel, CredentialField, ProbeResult, SourceAdapter
from .errors import SourceCredentialsMissing, SourceError
from .hosts import domain
from .profile import term_pairs
from .text import html_to_text

LIMIT = 40


class MastodonSource(SourceAdapter):
    id = "mastodon"
    display_name = "Mastodon"
    terms_url = "https://docs.joinmastodon.org/api/guidelines/"
    commercial_use_allowed = False
    requires_credentials = True
    credential_fields = (
        CredentialField(name="instance", env_var="RIR_MASTODON_INSTANCE", secret=False),
        CredentialField(name="access_token", env_var="RIR_MASTODON_ACCESS_TOKEN"),
    )
    cost_model = CostModel(unit="request", note="300 peticiones cada 5 min por cuenta")

    def _instancia(self) -> str:
        valor = domain(str(self.credentials.get("instance") or ""))
        if valor is None:
            raise SourceCredentialsMissing(self.id, "instance debe ser un dominio (p. ej. mastodon.social)")
        return valor

    async def _buscar(self, q: str, limite: int) -> Any:
        instancia = self._instancia()
        return await self._get(
            f"https://{instancia}/api/v2/search",
            params={"q": q, "type": "statuses", "limit": limite, "resolve": "false"},
            headers={"Authorization": f"Bearer {self.credentials.get('access_token', '')}"})

    def _leer_cuota(self, cabeceras: httpx.Headers) -> None:
        reinicio = cabeceras.get("X-RateLimit-Reset")
        super()._leer_cuota(cabeceras)
        if reinicio and not reinicio.replace(".", "", 1).isdigit():
            try:
                self.quota.reset_epoch = datetime.fromisoformat(reinicio).timestamp()
            except ValueError:
                self.quota.reset_epoch = None

    async def probe(self) -> ProbeResult:
        try:
            await self._buscar("the", 1)
        except SourceError as exc:
            return self._probe_error(exc)
        return self._probe_ok(f"{self._instancia()} respondió a una búsqueda con el token")

    async def search(self, query: SearchQuery) -> AsyncIterator[EvidenceItem]:
        instancia = self._instancia()
        restantes = self.budget.max_requests - self.budget.spent_requests
        vistos: set[str] = set()
        for palabra, frase in term_pairs(query, limit=restantes):
            partes = [palabra] if palabra else []
            if frase:
                partes.append(f'"{frase}"')
            datos = await self._buscar(" ".join(partes), LIMIT)
            for estado in datos.get("statuses") or []:
                item = self._convertir(estado, instancia, query.since)
                if item is None or item.id in vistos:
                    continue
                vistos.add(item.id)
                yield item

    def _convertir(self, estado: dict[str, Any], instancia: str,
                   since: datetime | None) -> EvidenceItem | None:
        nativo, creado = estado.get("id"), estado.get("created_at")
        if not nativo or not creado or estado.get("visibility") != "public":
            return None
        cuando = datetime.fromisoformat(str(creado))
        if since is not None and cuando < since:
            return None
        texto = html_to_text(estado.get("content"))
        if not texto:
            return None
        cuenta = estado.get("account") or {}
        acct = str(cuenta.get("acct") or "")
        servidor = acct.split("@", 1)[1] if "@" in acct else instancia
        return self._item(
            nativo=f"{instancia}:{nativo}", community=servidor, kind="post", text=texto,
            url=f"https://{instancia}/api/v1/statuses/{nativo}",
            author=f"{instancia}:{cuenta.get('id')}" if cuenta.get("id") else None,
            created_at=cuando, language=estado.get("language"),
            engagement=Engagement(replies=estado.get("replies_count"),
                                  reactions=estado.get("favourites_count")),
            native={"reblogs": estado.get("reblogs_count"), "sensitive": estado.get("sensitive")},
        )
