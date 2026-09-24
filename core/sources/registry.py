"""
Registro de fuentes y estado verificado (F2.4, F2.8)
====================================================

Estado de una fuente, en este orden de precedencia:

1. `deshabilitada_por_usuario`: el usuario la apagó.
2. `no_configurada`: le faltan credenciales obligatorias.
3. `error` (con código): la última llamada real falló.
4. `verificada` (con hora): la última llamada real respondió.
5. `configurada_sin_verificar`: todavía no hay respuesta real.

Verde solo con una respuesta real de la API (AUD-004). Una fuente no
conectada no es origen de nada, y el modo comercial excluye las que no
permiten uso comercial.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol

from pydantic import BaseModel

from core.storage.postgres_store import DEFAULT_TENANT_ID

from .base import ProbeResult, SourceAdapter

if TYPE_CHECKING:
    import psycopg

SourceStatusName = Literal[
    "no_configurada", "configurada_sin_verificar", "verificada", "error",
    "deshabilitada_por_usuario",
]

#: Preferencia del .env: 1 = modo comercial (se excluyen las de uso personal).
COMMERCIAL_MODE_ENV = "RIR_COMMERCIAL_MODE"


@dataclass(frozen=True)
class SavedSourceState:
    """Lo guardado de una fuente: lo último que dijo su API y si está apagada."""

    source: str
    status: SourceStatusName = "configurada_sin_verificar"
    last_verified_at: datetime | None = None
    error_code: str | None = None
    detail: str | None = None
    disabled: bool = False


class SourcesStateRepository(Protocol):
    def get(self, source: str) -> SavedSourceState | None: ...

    def record_probe(self, source: str, result: ProbeResult) -> None: ...

    def set_disabled(self, source: str, disabled: bool) -> None: ...

    def reset(self, source: str) -> None: ...


def _tras_probar(previo: SavedSourceState, result: ProbeResult) -> SavedSourceState:
    if result.ok:
        return replace(previo, status="verificada", last_verified_at=result.checked_at,
                       error_code=None, detail=result.detail)
    return replace(previo, status="error", error_code=result.code or "source_error",
                   detail=result.detail)


class InMemorySourcesState:
    """Mismo contrato que PostgreSQL, en memoria (tests, sidecar sin base)."""

    def __init__(self) -> None:
        self._estados: dict[str, SavedSourceState] = {}

    def get(self, source: str) -> SavedSourceState | None:
        return self._estados.get(source)

    def record_probe(self, source: str, result: ProbeResult) -> None:
        previo = self._estados.get(source, SavedSourceState(source))
        self._estados[source] = _tras_probar(previo, result)

    def set_disabled(self, source: str, disabled: bool) -> None:
        previo = self._estados.get(source, SavedSourceState(source))
        self._estados[source] = replace(previo, disabled=disabled)

    def reset(self, source: str) -> None:
        """Credenciales nuevas: lo verificado antes ya no vale."""
        previo = self._estados.get(source, SavedSourceState(source))
        self._estados[source] = SavedSourceState(source, disabled=previo.disabled)


class PostgresSourcesState:
    """`sources_state` en PostgreSQL (conexión síncrona: la usan rutas síncronas)."""

    def __init__(self, dsn: str, tenant_id: str = DEFAULT_TENANT_ID) -> None:
        self.dsn = dsn
        self.tenant_id = tenant_id

    def _conectar(self) -> psycopg.Connection[dict[str, Any]]:
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self.dsn, row_factory=dict_row,
                               options="-c search_path=radar,public")

    def get(self, source: str) -> SavedSourceState | None:
        with self._conectar() as conn:
            fila = conn.execute(
                "SELECT source, status, last_verified_at, error_code, detail, disabled "
                "FROM sources_state WHERE tenant_id = %s AND source = %s",
                (self.tenant_id, source),
            ).fetchone()
        return SavedSourceState(**fila) if fila else None

    def _guardar(self, estado: SavedSourceState) -> None:
        with self._conectar() as conn:
            conn.execute(
                """
                INSERT INTO sources_state (tenant_id, source, status, last_verified_at,
                    error_code, detail, disabled, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (tenant_id, source) DO UPDATE SET
                    status = EXCLUDED.status, last_verified_at = EXCLUDED.last_verified_at,
                    error_code = EXCLUDED.error_code, detail = EXCLUDED.detail,
                    disabled = EXCLUDED.disabled, updated_at = now()
                """,
                (self.tenant_id, estado.source, estado.status, estado.last_verified_at,
                 estado.error_code, estado.detail, estado.disabled),
            )

    def record_probe(self, source: str, result: ProbeResult) -> None:
        self._guardar(_tras_probar(self.get(source) or SavedSourceState(source), result))

    def set_disabled(self, source: str, disabled: bool) -> None:
        self._guardar(replace(self.get(source) or SavedSourceState(source), disabled=disabled))

    def reset(self, source: str) -> None:
        previo = self.get(source) or SavedSourceState(source)
        self._guardar(SavedSourceState(source, disabled=previo.disabled))


class CredentialState(BaseModel):
    """Qué credencial hay, nunca su valor."""

    name: str
    env_var: str
    secret: bool
    required: bool
    configured: bool


class SourceStatus(BaseModel):
    source: str
    display_name: str
    terms_url: str
    commercial_use_allowed: bool
    requires_credentials: bool
    credential_fields: list[CredentialState]
    status: SourceStatusName
    last_verified_at: datetime | None
    error_code: str | None
    detail: str | None
    disabled: bool
    excluded_by_commercial_mode: bool
    #: Entra en el escaneo: conectada, encendida y permitida por el modo comercial.
    active: bool
    cost_unit: str
    cost_note: str


def credentials_for(fuente: type[SourceAdapter], env: Mapping[str, str]) -> dict[str, str]:
    """Las credenciales presentes de una fuente, por nombre de campo."""
    return {
        campo.name: env[campo.env_var].strip()
        for campo in fuente.credential_fields
        if (env.get(campo.env_var) or "").strip()
    }


def source_status(
    fuente: type[SourceAdapter],
    env: Mapping[str, str],
    guardado: SavedSourceState | None,
    commercial_mode: bool,
) -> SourceStatus:
    presentes = credentials_for(fuente, env)
    campos = [
        CredentialState(name=c.name, env_var=c.env_var, secret=c.secret, required=c.required,
                        configured=c.name in presentes)
        for c in fuente.credential_fields
    ]
    faltan = any(c.required and not c.configured for c in campos)
    guardado = guardado or SavedSourceState(fuente.id, disabled=fuente.disabled_by_default)

    estado: SourceStatusName
    detalle = guardado.detail
    if guardado.disabled:
        estado = "deshabilitada_por_usuario"
    elif fuente.pending_approval:
        estado, detalle = "no_configurada", fuente.pending_approval
    elif fuente.requires_credentials and faltan:
        estado = "no_configurada"
    else:
        estado = guardado.status

    excluida = commercial_mode and not fuente.commercial_use_allowed
    return SourceStatus(
        source=fuente.id,
        display_name=fuente.display_name,
        terms_url=fuente.terms_url,
        commercial_use_allowed=fuente.commercial_use_allowed,
        requires_credentials=fuente.requires_credentials,
        credential_fields=campos,
        status=estado,
        last_verified_at=guardado.last_verified_at,
        error_code=guardado.error_code if estado == "error" else None,
        detail=detalle,
        disabled=guardado.disabled,
        excluded_by_commercial_mode=excluida,
        active=(estado not in ("no_configurada", "deshabilitada_por_usuario") and not excluida
                and not (estado == "error" and guardado.error_code in ERRORES_QUE_EXCLUYEN)),
        cost_unit=fuente.cost_model.unit,
        cost_note=fuente.cost_model.note,
    )


#: Errores que no se arreglan solos (AUD2-012, DP10 A): hasta una prueba con
#: éxito la fuente no entra en el escaneo, que gastaría una llamada destinada
#: a fallar. Lo pasajero (caída, cuota) sí entra: se recupera sin el usuario.
ERRORES_QUE_EXCLUYEN = frozenset({"source_auth_failed", "source_forbidden", "source_not_found"})


def active_sources(
    fuentes: Iterable[type[SourceAdapter]],
    env: Mapping[str, str],
    repo: SourcesStateRepository,
    commercial_mode: bool,
) -> list[type[SourceAdapter]]:
    """Las fuentes que entran en un escaneo: conectadas, encendidas y permitidas."""
    return [f for f in fuentes
            if source_status(f, env, repo.get(f.id), commercial_mode).active]
