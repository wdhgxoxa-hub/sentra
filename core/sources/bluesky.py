"""
Fuente: Bluesky (API oficial del AT Protocol)
=============================================

Sesión con com.atproto.server.createSession (identificador y contraseña de
app, nunca la contraseña de la cuenta) y búsqueda con
app.bsky.feed.searchPosts, autenticada, a través de bsky.social.

- createSession tiene un límite bajo por cuenta: la sesión se guarda en
  memoria (por huella del identificador, nunca la contraseña) y se reutiliza
  entre escaneos hasta que caduca; un token caducado se renueva una vez.
- La cuota llega en ratelimit-limit/-remaining/-reset (sin el prefijo X-).
- D-M7 (R5 frente a R9): la URL del original lleva el DID, no el @handle:
  https://bsky.app/profile/<did>/post/<rkey>. El autor, solo como hash.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from core.evidence.model import Engagement, EvidenceItem, SearchQuery

from .base import CostModel, CredentialField, ProbeResult, SourceAdapter, _numero
from .errors import SourceAuthFailed, SourceError
from .profile import term_pairs

SERVICE = "https://bsky.social"
WEB = "https://bsky.app"
LIMIT = 100
#: El accessJwt dura unas dos horas; se renueva antes.
SESSION_TTL_S = 90 * 60


class BlueskySource(SourceAdapter):
    id = "bluesky"
    display_name = "Bluesky"
    terms_url = "https://docs.bsky.app/docs/support/developer-guidelines"
    commercial_use_allowed = True
    requires_credentials = True
    credential_fields = (
        CredentialField(name="identifier", env_var="RIR_BLUESKY_IDENTIFIER", secret=False),
        CredentialField(name="app_password", env_var="RIR_BLUESKY_APP_PASSWORD"),
    )
    cost_model = CostModel(
        unit="request",
        note="3.000 peticiones cada 5 min por IP; sesiones: 30 cada 5 min por cuenta",
    )

    #: Sesiones por huella del identificador: (accessJwt, caduca_en monotónico).
    sessions: ClassVar[dict[str, tuple[str, float]]] = {}

    def _huella(self) -> str:
        return hashlib.sha256(str(self.credentials.get("identifier", "")).encode()).hexdigest()

    async def _jwt(self, *, renovar: bool = False) -> str:
        guardada = self.sessions.get(self._huella())
        if guardada and not renovar and time.monotonic() < guardada[1]:
            return guardada[0]
        respuesta = await self._request(
            "POST", f"{SERVICE}/xrpc/com.atproto.server.createSession",
            json={"identifier": self.credentials.get("identifier", ""),
                  "password": self.credentials.get("app_password", "")})
        jwt = (respuesta.json() or {}).get("accessJwt")
        if not jwt:
            raise SourceAuthFailed(self.id, "createSession no devolvió accessJwt")
        self.sessions[self._huella()] = (str(jwt), time.monotonic() + SESSION_TTL_S)
        return str(jwt)

    async def _buscar(self, params: dict[str, Any]) -> Any:
        url = f"{SERVICE}/xrpc/app.bsky.feed.searchPosts"
        # Fuera del try: si falla la sesión (contraseña mala) no se reintenta.
        jwt = await self._jwt()
        try:
            return await self._get(url, params=params, headers={"Authorization": f"Bearer {jwt}"})
        except SourceAuthFailed:
            # Token caducado o revocado: una sesión nueva, una sola vez.
            return await self._get(url, params=params, headers={
                "Authorization": f"Bearer {await self._jwt(renovar=True)}"})

    def _leer_cuota(self, cabeceras: httpx.Headers) -> None:
        super()._leer_cuota(cabeceras)
        if (limite := _numero(cabeceras.get("ratelimit-limit"))) is not None:
            self.quota.limit = int(limite)
        if (restante := _numero(cabeceras.get("ratelimit-remaining"))) is not None:
            self.quota.remaining = int(restante)
        if (reinicio := _numero(cabeceras.get("ratelimit-reset"))) is not None:
            self.quota.reset_epoch = reinicio

    async def probe(self) -> ProbeResult:
        try:
            await self._buscar({"q": "the", "limit": 1})
        except SourceError as exc:
            return self._probe_error(exc)
        return self._probe_ok("Bluesky abrió sesión y respondió a una búsqueda")

    async def search(self, query: SearchQuery) -> AsyncIterator[EvidenceItem]:
        restantes = self.budget.max_requests - self.budget.spent_requests
        vistos: set[str] = set()
        # La sesión también gasta una petición.
        # Solo el tema: con la frase entre comillas, 0 resultados (medido; F2).
        for palabra, frase in term_pairs(query, limit=max(1, restantes - 1), solo_tema=True):
            partes = [palabra] if palabra else []
            if frase:
                partes.append(f'"{frase}"')
            params: dict[str, Any] = {"q": " ".join(partes), "sort": "latest", "limit": LIMIT}
            if query.since is not None:
                params["since"] = query.since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            datos = await self._buscar(params)
            for post in datos.get("posts") or []:
                item = self._convertir(post)
                if item is None or item.id in vistos:
                    continue
                vistos.add(item.id)
                yield item

    def _convertir(self, post: dict[str, Any]) -> EvidenceItem | None:
        uri = str(post.get("uri") or "")
        # at://<did>/app.bsky.feed.post/<rkey>
        partes = uri.removeprefix("at://").split("/")
        registro = post.get("record") or {}
        texto = str(registro.get("text") or "").strip()
        creado = registro.get("createdAt")
        if len(partes) != 3 or partes[1] != "app.bsky.feed.post" or not texto or not creado:
            return None
        did, rkey = partes[0], partes[2]
        idiomas = registro.get("langs") or []
        return self._item(
            nativo=f"{did}/{rkey}", community="Bluesky", kind="post", text=texto,
            url=f"{WEB}/profile/{did}/post/{rkey}",
            author=(post.get("author") or {}).get("did"),
            created_at=datetime.fromisoformat(str(creado)),
            language=str(idiomas[0]) if idiomas else None,
            engagement=Engagement(replies=post.get("replyCount"),
                                  reactions=post.get("likeCount")),
            native={"reposts": post.get("repostCount"), "quotes": post.get("quoteCount")},
        )
