"""
Fuente: Stack Exchange (API oficial v2.3)
=========================================

GET https://api.stackexchange.com/2.3/search/advanced con el filtro
`withbody`: preguntas con su cuerpo en HTML, que se limpia. Solo lectura
anónima: la clave de la app (RIR_STACKEXCHANGE_KEY, opcional) sube la
cuota diaria por IP de 300 a 10.000; OAuth no se usa porque SENTRA nunca
actúa en nombre de nadie.

Reglas de la documentación (api.stackexchange.com/docs/throttle) que se
cumplen aquí:
- `backoff` en una respuesta: no volver a ese método hasta que pase.
- Más de 30 peticiones por segundo por IP es abuso: se espaciar a 25/s.
- Ninguna petición idéntica antes de un minuto: se reutiliza la respuesta.
- `quota_remaining` a 0: no se pide más.

Términos de la API: atribución visible (la red Stack Exchange como fuente,
el sitio y la URL del original en texto plano; ver
core/sources/attribution.py) y uso comercial remitido a las soluciones de
pago: solo uso personal.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from core.evidence.model import Engagement, EvidenceItem, SearchQuery

from .base import CostModel, CredentialField, ProbeResult, SourceAdapter
from .errors import (
    SourceAuthFailed,
    SourceCredentialsMissing,
    SourceError,
    SourceForbidden,
    SourceNotFound,
    SourceRateLimited,
    SourceUnavailable,
)
from .profile import term_pairs
from .sitios_stackexchange import SITIOS
from .text import html_to_text

API = "https://api.stackexchange.com/2.3"
DEFAULT_SITE = "stackoverflow"
PAGE_SIZE = 50

#: Tope de la documentación: más de 30 peticiones/s por IP es abuso.
MAX_REQUESTS_PER_SECOND = 30
#: Se va por debajo del tope con margen.
MIN_INTERVAL_S = 1 / 25
#: «No application should make semantically identical requests more than once a minute.»
IDENTICAL_REQUEST_WINDOW_S = 60.0
#: Un throttle_violation banea de 30 s a unos minutos: no se reintenta dentro del escaneo.
THROTTLE_BAN_S = 60.0

#: Nombre visible de cada sitio del catálogo; el resto, por el dominio del enlace.
SITE_NAMES: dict[str, str] = SITIOS

#: Respuestas recientes por petición (sin la clave): compartidas entre escaneos.
_RECIENTES: dict[str, tuple[float, Any]] = {}


class StackExchangeSource(SourceAdapter):
    id = "stackexchange"
    display_name = "Stack Exchange"
    terms_url = "https://stackexchange.com/legal/api-terms-of-use"
    #: DP5 A (AUD2-018): el contenido de Stack Exchange es CC BY-SA 4.0; se cita
    #: con la licencia y el enlace al original, donde se ve el autor (R9).
    content_license = ("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/")
    commercial_use_allowed = False
    requires_credentials = False
    credential_fields = (
        CredentialField(name="key", env_var="RIR_STACKEXCHANGE_KEY", required=False),
    )
    cost_model = CostModel(
        unit="request",
        note="Cuota diaria por IP: 300 sin clave, 10.000 con clave; respeta backoff",
    )

    #: Reloj monotónico; los tests lo sustituyen.
    clock: Callable[[], float] = staticmethod(time.monotonic)
    def __init__(self, *, recent: dict[str, tuple[float, Any]] | None = None,
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        #: Respuestas recientes por huella de la petición. Por defecto, las del
        #: proceso: la regla de la API es por IP. Los tests pasan la suya.
        self.recent = _RECIENTES if recent is None else recent
        self._ultima: float | None = None
        self._backoff_hasta: dict[str, float] = {}
        self._cuota_agotada = False

    # --- HTTP con las reglas de la API -----------------------------------------------

    def _params(self, params: Mapping[str, Any]) -> dict[str, Any]:
        completos = dict(params)
        if clave := self.credentials.get("key"):
            completos["key"] = clave
        return completos

    async def _esperar(self, segundos: float, motivo: str) -> None:
        if segundos <= 0:
            return
        if segundos > self.MAX_WAIT_S:
            raise SourceRateLimited(self.id, f"{motivo}: {segundos:.0f} s", retry_after=segundos)
        await self._sleep(segundos)

    async def _pedir(self, metodo: str, params: Mapping[str, Any]) -> Any:
        """GET a un método de la API respetando cuota, backoff y ritmo."""
        huella = f"{metodo}?{sorted(params.items())}"
        guardada = self.recent.get(huella)
        if guardada is not None and self.clock() - guardada[0] < IDENTICAL_REQUEST_WINDOW_S:
            return guardada[1]
        if self._cuota_agotada:
            raise SourceRateLimited(self.id, "cuota diaria agotada (quota_remaining = 0)")
        await self._esperar(self._backoff_hasta.get(metodo, 0.0) - self.clock(), "backoff")
        if self._ultima is not None:
            await self._esperar(MIN_INTERVAL_S - (self.clock() - self._ultima), "ritmo")
        self._ultima = self.clock()
        datos = await self._get(f"{API}{metodo}", params=self._params(params))

        restante, maximo = datos.get("quota_remaining"), datos.get("quota_max")
        if isinstance(restante, int):
            self.quota.remaining = restante
            self._cuota_agotada = restante <= 0
        if isinstance(maximo, int):
            self.quota.limit = maximo
        if isinstance(backoff := datos.get("backoff"), int | float):
            self._backoff_hasta[metodo] = self.clock() + float(backoff)
        self.recent[huella] = (self.clock(), datos)
        return datos

    def _error_de(self, respuesta: httpx.Response) -> SourceError:
        try:
            cuerpo = respuesta.json()
        except ValueError:
            return super()._error_de(respuesta)
        if not isinstance(cuerpo, dict) or "error_name" not in cuerpo:
            return super()._error_de(respuesta)
        nombre = str(cuerpo.get("error_name"))
        mensaje = str(cuerpo.get("error_message") or "")
        detalle = f"{nombre} ({cuerpo.get('error_id')})"
        if nombre == "throttle_violation":
            return SourceRateLimited(self.id, detalle, retry_after=THROTTLE_BAN_S)
        if nombre == "key_required":
            return SourceCredentialsMissing(self.id, detalle)
        if nombre == "bad_parameter" and "key" in mensaje.lower() and self.credentials.get("key"):
            return SourceAuthFailed(self.id, f"{detalle}: la clave no es válida")
        if nombre in ("access_denied", "access_token_required", "invalid_access_token"):
            return SourceForbidden(self.id, detalle)
        if nombre == "no_method":
            return SourceNotFound(self.id, detalle)
        if nombre in ("internal_error", "temporarily_unavailable"):
            return SourceUnavailable(self.id, detalle)
        return SourceError(self.id, detalle)

    # --- Contrato de fuente -----------------------------------------------------------

    async def probe(self) -> ProbeResult:
        try:
            await self._pedir("/info", {"site": DEFAULT_SITE})
        except SourceError as exc:
            return self._probe_error(exc)
        restante = self.quota.remaining if self.quota.remaining is not None else "?"
        maximo = self.quota.limit if self.quota.limit is not None else "?"
        return self._probe_ok(f"API de Stack Exchange respondió (cuota: {restante} de {maximo})")

    @staticmethod
    def _objetivos(query: SearchQuery) -> list[tuple[str, str | None]]:
        """(sitio, tag) de los objetivos del perfil: 'superuser' o 'superuser:excel'."""
        objetivos = []
        for objetivo in query.targets.get("stackexchange", []) or [DEFAULT_SITE]:
            sitio, _, tag = objetivo.strip().partition(":")
            if sitio:
                objetivos.append((sitio, tag or None))
        return objetivos or [(DEFAULT_SITE, None)]

    async def search(self, query: SearchQuery) -> AsyncIterator[EvidenceItem]:
        objetivos = self._objetivos(query)
        restantes = self.budget.max_requests - self.budget.spent_requests
        # Solo el tema: tema + frase daba 0–1 resultados (medido; tema solo, 21–30).
        pares = term_pairs(query, limit=max(1, restantes // len(objetivos)), solo_tema=True)
        vistos: set[str] = set()
        for palabra, frase in pares:
            for sitio, tag in objetivos:
                params: dict[str, Any] = {
                    "site": sitio, "q": " ".join(t for t in (palabra, frase) if t),
                    "filter": "withbody", "order": "desc", "sort": "relevance",
                    "pagesize": PAGE_SIZE,
                }
                if tag:
                    params["tagged"] = tag
                if query.since is not None:
                    params["fromdate"] = int(query.since.timestamp())
                datos = await self._pedir("/search/advanced", params)
                for pregunta in datos.get("items") or []:
                    item = self._convertir(pregunta, sitio)
                    if item is None or item.id in vistos:
                        continue
                    vistos.add(item.id)
                    yield item

    def _convertir(self, pregunta: dict[str, Any], sitio: str) -> EvidenceItem | None:
        nativo, enlace = pregunta.get("question_id"), pregunta.get("link")
        creado = pregunta.get("creation_date")
        if nativo is None or not enlace or creado is None:
            return None
        titulo = html_to_text(pregunta.get("title")) or None
        texto = html_to_text(pregunta.get("body")) or (titulo or "")
        if not texto:
            return None
        nombre_sitio = SITE_NAMES.get(sitio) or urlparse(str(enlace)).netloc or sitio
        return self._item(
            nativo=f"{sitio}:{nativo}", community=nombre_sitio, kind="question",
            title=titulo, text=texto, url=str(enlace),
            author=(pregunta.get("owner") or {}).get("display_name"),
            created_at=datetime.fromtimestamp(int(creado), UTC),
            engagement=Engagement(score=pregunta.get("score"),
                                  replies=pregunta.get("answer_count"),
                                  views=pregunta.get("view_count")),
            native={"site": sitio, "is_answered": pregunta.get("is_answered"),
                    "tags": list(pregunta.get("tags") or [])},
        )
