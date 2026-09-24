"""
Fuente: GitHub (API REST oficial, búsqueda de issues)
=====================================================

GET https://api.github.com/search/issues con la versión 2022-11-28. Solo
issues: un pull request es una solución propuesta, no una queja. El token
es opcional: sin él la búsqueda permite 10 peticiones por minuto; con él,
30. Una cuota agotada llega como 403 con X-RateLimit-Remaining: 0, y la
base la trata como límite de uso, no como acceso denegado.

La sonda consulta /rate_limit, que según la documentación no gasta cuota.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from core.evidence.model import Engagement, EvidenceItem, SearchQuery

from .base import CostModel, CredentialField, ProbeResult, SourceAdapter
from .errors import SourceError
from .profile import term_pairs

API = "https://api.github.com"
API_VERSION = "2022-11-28"

#: Resultados por búsqueda (máximo de la API: 100).
PER_PAGE = 50


class GitHubSource(SourceAdapter):
    id = "github"
    display_name = "GitHub"
    terms_url = "https://docs.github.com/en/site-policy/github-terms/github-terms-of-service"
    commercial_use_allowed = True
    requires_credentials = False
    credential_fields = (
        CredentialField(name="token", env_var="RIR_GITHUB_TOKEN", required=False),
    )
    cost_model = CostModel(unit="request", note="Búsqueda: 10 peticiones/min sin token, 30 con token")

    def _cabeceras(self) -> dict[str, str]:
        cabeceras = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION}
        if token := self.credentials.get("token"):
            cabeceras["Authorization"] = f"Bearer {token}"
        return cabeceras

    async def probe(self) -> ProbeResult:
        try:
            datos = await self._get(f"{API}/rate_limit", headers=self._cabeceras())
        except SourceError as exc:
            return self._probe_error(exc)
        busqueda = (datos.get("resources") or {}).get("search") or {}
        return self._probe_ok(
            f"API de GitHub respondió (búsqueda: {busqueda.get('remaining', '?')} de "
            f"{busqueda.get('limit', '?')} peticiones disponibles)")

    def _q(self, palabra: str | None, frase: str | None, query: SearchQuery) -> str:
        partes = [f'"{t}"' for t in (palabra, frase) if t]
        partes.append("is:issue")
        partes += [f"repo:{r}" for r in query.targets.get(self.id, []) if "/" in r]
        if query.since is not None:
            partes.append(f"created:>={query.since.date().isoformat()}")
        return " ".join(partes)

    async def search(self, query: SearchQuery) -> AsyncIterator[EvidenceItem]:
        restantes = self.budget.max_requests - self.budget.spent_requests
        vistos: set[str] = set()
        # Solo el tema: con la frase exigida daba 0–1 resultados (medido; tema solo, 30).
        for palabra, frase in term_pairs(query, limit=restantes, solo_tema=True):
            datos = await self._get(
                f"{API}/search/issues", headers=self._cabeceras(),
                params={"q": self._q(palabra, frase, query), "per_page": PER_PAGE})
            for issue in datos.get("items") or []:
                item = self._convertir(issue)
                if item is None or item.id in vistos:
                    continue
                vistos.add(item.id)
                yield item

    def _convertir(self, issue: dict[str, Any]) -> EvidenceItem | None:
        if "pull_request" in issue:
            return None
        nativo, url = issue.get("id"), issue.get("html_url")
        creado = issue.get("created_at")
        if nativo is None or not url or not creado:
            return None
        titulo = str(issue.get("title") or "").strip()
        cuerpo = str(issue.get("body") or "").replace("\r\n", "\n").strip()
        texto = cuerpo or titulo
        if not texto:
            return None
        repo = str(issue.get("repository_url") or "").removeprefix(f"{API}/repos/")
        reacciones = (issue.get("reactions") or {}).get("total_count")
        return self._item(
            nativo=str(nativo), community=repo or "GitHub", kind="issue",
            title=titulo or None, text=texto, url=str(url),
            author=(issue.get("user") or {}).get("login"),
            created_at=datetime.fromisoformat(str(creado)),
            engagement=Engagement(replies=issue.get("comments"), reactions=reacciones),
            native={"number": issue.get("number"), "state": issue.get("state"),
                    "labels": [lab.get("name") for lab in issue.get("labels") or []
                               if isinstance(lab, dict)]},
        )
