"""
Contrato de adaptador de fuente (F2.1)
======================================

Cada fuente implementa `probe()` y `search()` y declara sus términos, su
uso comercial, sus credenciales y su modelo de costo. Lo común vive aquí:

- solo APIs oficiales y documentadas, con un User-Agent que identifica a
  SENTRA (R4, R5): nada de suplantar un navegador ni de cookies de sesión;
- errores tipados a partir del estado HTTP; un fallo nunca es «0 resultados»;
- Retry-After y X-RateLimit-* respetados; los fallos transitorios se
  reintentan con espera creciente, y una espera larga se devuelve como
  error con su valor en lugar de bloquear el escaneo;
- presupuesto comprobado antes de cada petición y de cada ítem;
- el autor solo como hash salado, con la fuente delante (R9).
"""

from __future__ import annotations

import asyncio
import email.utils
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal

import httpx
from pydantic import BaseModel

from core.evidence.author import author_hash
from core.evidence.model import Engagement, EvidenceItem, EvidenceKind, SearchQuery

from .budget import SourceBudget
from .errors import (
    SourceAuthFailed,
    SourceError,
    SourceForbidden,
    SourceNotFound,
    SourceRateLimited,
    SourceUnavailable,
)

SENTRA_VERSION = "0.1.0"

#: Identifica a SENTRA ante cada plataforma (R5). Nunca un navegador (R4).
USER_AGENT = f"SENTRA/{SENTRA_VERSION} (+https://github.com/wdhgxoxa-hub/sentra)"

#: Timeout de cada petición a una fuente.
REQUEST_TIMEOUT_S = 20.0


class CostModel(BaseModel):
    """Cuánto cuesta cada operación, para la contabilidad del escaneo."""

    unit: Literal["request", "quota_unit", "usd"]
    per_request: float = 0.0
    per_item: float = 0.0
    note: str = ""


class CredentialField(BaseModel):
    """Un dato de acceso que la fuente necesita (se guarda en el .env)."""

    name: str
    env_var: str
    secret: bool = True
    required: bool = True


class ProbeResult(BaseModel):
    """Resultado de una llamada mínima real a la API."""

    ok: bool
    code: str | None = None
    detail: str = ""
    checked_at: datetime


@dataclass
class Quota:
    """Lo último que dijo la plataforma sobre su cuota (None = no lo dice)."""

    limit: int | None = None
    remaining: int | None = None
    reset_epoch: float | None = None


def _numero(valor: str | None) -> float | None:
    try:
        return float(valor) if valor is not None else None
    except ValueError:
        return None


def _retry_after(cabeceras: httpx.Headers) -> float | None:
    """Segundos del Retry-After, en segundos o como fecha HTTP."""
    valor = cabeceras.get("Retry-After")
    if valor is None:
        return None
    segundos = _numero(valor)
    if segundos is not None:
        return max(segundos, 0.0)
    try:
        cuando = email.utils.parsedate_to_datetime(valor)
    except (TypeError, ValueError):
        return None
    return max((cuando - datetime.now(UTC)).total_seconds(), 0.0)


class SourceAdapter(ABC):
    """Una fuente de evidencia con API oficial."""

    id: ClassVar[str]
    display_name: ClassVar[str]
    terms_url: ClassVar[str]
    commercial_use_allowed: ClassVar[bool]
    requires_credentials: ClassVar[bool]
    credential_fields: ClassVar[tuple[CredentialField, ...]] = ()
    cost_model: ClassVar[CostModel]
    #: Motivo por el que la fuente aún no puede hacer llamadas reales (R7); None = puede.
    #: Con motivo: nunca entra en un escaneo y «Probar» no sale a la red.
    pending_approval: ClassVar[str | None] = None
    #: Días que los términos dejan guardar la evidencia sin refrescarla; None = sin límite.
    retention_days: ClassVar[int | None] = None

    @classmethod
    def default_budget(cls) -> SourceBudget:
        """Presupuesto de un escaneo (D-M4); las fuentes con cuota propia lo cambian."""
        return SourceBudget(source=cls.id)

    #: Espera máxima que se acepta dentro del escaneo; más larga, error con su valor.
    MAX_WAIT_S: ClassVar[float] = 30.0
    #: Reintentos tras el primer intento ante un fallo transitorio.
    MAX_RETRIES: ClassVar[int] = 2
    BACKOFF_S: ClassVar[float] = 1.0

    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        budget: SourceBudget,
        credentials: Mapping[str, str],
        author_salt: str,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.http = http
        self.budget = budget
        if not budget.source:
            budget.source = self.id
        self.credentials = dict(credentials)
        self._author_salt = author_salt
        self._sleep = sleep
        self.quota = Quota()

    # --- Lo que cada fuente implementa ------------------------------------------

    @abstractmethod
    async def probe(self) -> ProbeResult:
        """Llamada mínima real a la API: verde solo con respuesta real."""

    @abstractmethod
    def search(self, query: SearchQuery) -> AsyncIterator[EvidenceItem]:
        """Evidencia que casa con la consulta, página a página."""

    # --- HTTP común --------------------------------------------------------------

    async def _get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        units: float = 0.0,
        usd: float = 0.0,
    ) -> Any:
        """GET con cuota, reintentos y errores tipados; devuelve el JSON."""
        respuesta = await self._request("GET", url, params=params, headers=headers,
                                        units=units, usd=usd)
        try:
            return respuesta.json()
        except ValueError as exc:
            raise SourceUnavailable(self.id, f"respuesta que no es JSON: {exc}") from None

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        json: Any = None,
        data: Mapping[str, str] | None = None,
        units: float = 0.0,
        usd: float = 0.0,
    ) -> httpx.Response:
        cabeceras = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
        for intento in range(self.MAX_RETRIES + 1):
            self.budget.charge_request(units=units, usd=usd)
            error: SourceError
            try:
                respuesta = await self.http.request(
                    method, url, params=params, headers=cabeceras, json=json, data=data,
                    timeout=REQUEST_TIMEOUT_S,
                )
            except httpx.TimeoutException:
                error = SourceUnavailable(self.id, "la API no respondió a tiempo")
            except httpx.TransportError as exc:
                error = SourceUnavailable(self.id, f"sin conexión con la API: {type(exc).__name__}")
            else:
                self._leer_cuota(respuesta.headers)
                if respuesta.status_code < 400:
                    return respuesta
                error = self._error_de(respuesta)

            if not error.transient or intento >= self.MAX_RETRIES:
                raise error
            espera = (
                error.retry_after
                if isinstance(error, SourceRateLimited) and error.retry_after is not None
                else self.BACKOFF_S * 2 ** intento
            )
            if espera > self.MAX_WAIT_S:
                raise error
            await self._sleep(espera)
        raise AssertionError("inalcanzable: el último intento devuelve o lanza")

    def _leer_cuota(self, cabeceras: httpx.Headers) -> None:
        limite = _numero(cabeceras.get("X-RateLimit-Limit"))
        restante = _numero(cabeceras.get("X-RateLimit-Remaining"))
        reinicio = _numero(cabeceras.get("X-RateLimit-Reset"))
        if limite is not None:
            self.quota.limit = int(limite)
        if restante is not None:
            self.quota.remaining = int(restante)
        if reinicio is not None:
            self.quota.reset_epoch = reinicio

    def _error_de(self, respuesta: httpx.Response) -> SourceError:
        estado = respuesta.status_code
        detalle = f"HTTP {estado}"
        agotada = respuesta.headers.get("X-RateLimit-Remaining") == "0"
        if estado == 429 or (estado == 403 and agotada):
            espera = _retry_after(respuesta.headers)
            if espera is None and self.quota.reset_epoch is not None:
                espera = max(self.quota.reset_epoch - time.time(), 0.0)
            return SourceRateLimited(self.id, f"{detalle}: cuota agotada", retry_after=espera)
        if estado == 401:
            return SourceAuthFailed(self.id, f"{detalle}: credenciales rechazadas")
        if estado == 403:
            return SourceForbidden(self.id, f"{detalle}: acceso denegado")
        if estado == 404:
            return SourceNotFound(self.id, f"{detalle}: no existe")
        if estado >= 500 or estado == 408:
            return SourceUnavailable(self.id, f"{detalle}: la API falló")
        return SourceError(self.id, f"{detalle}: petición rechazada")

    # --- Evidencia ---------------------------------------------------------------

    def _item(
        self,
        *,
        nativo: str,
        community: str,
        kind: EvidenceKind,
        text: str,
        url: str,
        author: str | None,
        created_at: datetime,
        title: str | None = None,
        language: str | None = None,
        thread: str | None = None,
        engagement: Engagement | None = None,
        native: Mapping[str, Any] | None = None,
    ) -> EvidenceItem:
        """Un EvidenceItem de esta fuente; cobra un ítem del presupuesto."""
        self.budget.charge_item()
        return EvidenceItem(
            id=f"{self.id}:{nativo}",
            source=self.id,
            community=community,
            kind=kind,
            title=title,
            text=text,
            url=url,
            author_hash=author_hash(self.id, author, self._author_salt),
            created_at=created_at,
            fetched_at=datetime.now(UTC),
            language=language,
            thread_id=f"{self.id}:{thread}" if thread else f"{self.id}:{nativo}",
            engagement=engagement or Engagement(),
            native_metrics=dict(native or {}),
            data_source="real",
        )

    def _probe_ok(self, detail: str) -> ProbeResult:
        return ProbeResult(ok=True, detail=detail, checked_at=datetime.now(UTC))

    def _probe_error(self, error: SourceError) -> ProbeResult:
        return ProbeResult(ok=False, code=error.code, detail=error.detail,
                           checked_at=datetime.now(UTC))
