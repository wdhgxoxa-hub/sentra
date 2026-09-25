"""
Punto único de control de Gemini (Fase 1, B4)
=============================================

Toda llamada a Gemini pasa por aquí: `GeminiProvider` no se crea sin un
`ControlDeGemini`. Antes de cada intento se comprueban el propósito y los
topes; después, el intento queda como una fila de `llm_usage` (migración
017): `ok` o `error` si salió, con sus tokens si el proveedor los informó, o
`cortada` si un tope no la dejó salir (con el motivo en `error_code`). Cada
reintento es una llamada real y cuenta como tal.

Topes (llm_budget_settings, se editan en Configuración):
- por escaneo, llamadas y tokens: lo que ha salido por este control;
- por día, llamadas y tokens: todo lo que ha salido hoy en hora de Lima.
El listado de modelos se registra, pero ni cuenta ni se corta (Walter).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import NamedTuple, Protocol

from .base import LLMBudgetExhausted

#: Los mismos que el CHECK de llm_usage (sql/migrations/017_uso_y_topes_de_gemini.sql).
PROPOSITOS = frozenset({"etiquetado", "g0", "abogado", "dossier", "plan", "prueba_clave",
                        "listado_modelos", "otros"})
RESULTADOS = frozenset({"ok", "error", "cortada"})
#: Registrado pero fuera de los topes (decisión de Walter).
SIN_TOPE = "listado_modelos"
#: Perú no cambia de hora desde 1994: UTC-5 fijo. PostgreSQL usa 'America/Lima'.
LIMA = timezone(timedelta(hours=-5), "America/Lima")

Reloj = Callable[[], datetime]


def _ahora() -> datetime:
    return datetime.now(UTC)


def dia_de_lima(momento: datetime) -> date:
    return momento.astimezone(LIMA).date()


class Topes(NamedTuple):
    scan_calls: int
    scan_tokens: int
    daily_calls: int
    daily_tokens: int


#: Los valores por defecto de la migración 017, aprobados por Walter.
TOPES_POR_DEFECTO = Topes(20, 500_000, 40, 1_000_000)


@dataclass(frozen=True)
class Intento:
    """Un intento de llamada. Tokens None = el proveedor no los informó."""

    model: str
    purpose: str
    outcome: str
    error_code: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None

    @property
    def tokens(self) -> int:
        return sum(t or 0 for t in (self.input_tokens, self.output_tokens, self.thinking_tokens))

    @property
    def cuenta(self) -> bool:
        """Si cuenta para los topes: salió (ok o error) y no es el listado."""
        return self.outcome != "cortada" and self.purpose != SIN_TOPE


class RegistroDeUso(Protocol):
    """Dónde queda cada intento y de dónde salen los topes."""

    def guardar(self, run_id: str | None, intento: Intento) -> int: ...

    def reasignar(self, ids: list[int], run_id: str) -> None: ...

    def topes(self) -> Topes: ...

    def uso_de_hoy(self, ahora: datetime) -> tuple[int, int]:
        """(llamadas, tokens) que cuentan, del día de Lima de `ahora`."""
        ...

    def medias_de_tokens(self) -> dict[str, float]:
        """Tokens medios por llamada que salió bien, por propósito (para estimar)."""
        ...

    def guardar_topes(self, topes: Topes) -> None:
        """Los topes que se editan en Configuración › Presupuesto de Gemini."""
        ...


class ControlDeGemini:
    """Lo que el proveedor consulta antes de cada intento y avisa después.

    `run_id` es la ejecución a la que se carga el uso; los documentos y el
    listado de modelos no son de ningún escaneo (None). `escaneo` activa el
    tope por escaneo (un escaneo o un re-juicio = un control). El re-juicio
    llama a Gemini antes de crear su ejecución: `asignar_ejecucion` se la da
    también a lo ya anotado por este control.
    """

    def __init__(self, registro: RegistroDeUso, *, run_id: str | None = None, escaneo: bool = False,
                 reloj: Reloj = _ahora) -> None:
        self._registro = registro
        self.run_id = run_id
        self._escaneo = escaneo
        self._reloj = reloj
        self._sin_ejecucion: list[int] = []
        self.llamadas = 0
        self.tokens = 0
        #: El primer tope que cortó una llamada: el motivo de parada de la ejecución.
        self.motivo_de_corte: str | None = None

    def asignar_ejecucion(self, run_id: str) -> None:
        self.run_id = run_id
        if self._sin_ejecucion:
            self._registro.reasignar(self._sin_ejecucion, run_id)
            self._sin_ejecucion = []

    def antes(self, purpose: str, model: str = "-") -> None:
        """Antes de cada intento: un propósito desconocido no sale; con un tope
        alcanzado tampoco, y queda su fila «cortada» con el motivo."""
        if purpose not in PROPOSITOS:
            raise ValueError(f"propósito de llamada desconocido: {purpose!r}")
        if purpose == SIN_TOPE:
            return
        motivo = self._tope_alcanzado()
        if motivo is not None:
            self.motivo_de_corte = self.motivo_de_corte or motivo
            self.anotar(Intento(model, purpose, "cortada", motivo))
            raise LLMBudgetExhausted(f"Tope de Gemini alcanzado: {motivo}", motivo=motivo)

    def _tope_alcanzado(self) -> str | None:
        topes = self._registro.topes()
        if self._escaneo:
            if self.llamadas >= topes.scan_calls:
                return "tope_escaneo_llamadas"
            if self.tokens >= topes.scan_tokens:
                return "tope_escaneo_tokens"
        llamadas, tokens = self._registro.uso_de_hoy(self._reloj())
        if llamadas >= topes.daily_calls:
            return "tope_diario_llamadas"
        if tokens >= topes.daily_tokens:
            return "tope_diario_tokens"
        return None

    def anotar(self, intento: Intento) -> None:
        if intento.outcome not in RESULTADOS:
            raise ValueError(f"resultado desconocido: {intento.outcome!r}")
        fila = self._registro.guardar(self.run_id, intento)
        if self.run_id is None:
            self._sin_ejecucion.append(fila)
        if intento.cuenta:
            self.llamadas += 1
            self.tokens += intento.tokens


class RegistroEnMemoria:
    """Registro del motor sin persistencia (tests, demo sin base): los intentos
    quedan en `filas` como (run_id, Intento), en orden, con su momento aparte."""

    def __init__(self, topes: Topes = TOPES_POR_DEFECTO, reloj: Reloj = _ahora) -> None:
        self.filas: list[tuple[str | None, Intento]] = []
        self._momentos: list[datetime] = []
        self._topes = topes
        self._reloj = reloj

    def guardar(self, run_id: str | None, intento: Intento) -> int:
        self.filas.append((run_id, intento))
        self._momentos.append(self._reloj())
        return len(self.filas) - 1

    def reasignar(self, ids: list[int], run_id: str) -> None:
        for i in ids:
            self.filas[i] = (run_id, self.filas[i][1])

    def topes(self) -> Topes:
        return self._topes

    def guardar_topes(self, topes: Topes) -> None:
        self._topes = topes

    def uso_de_hoy(self, ahora: datetime) -> tuple[int, int]:
        hoy = dia_de_lima(ahora)
        del_dia = [i for (_, i), m in zip(self.filas, self._momentos, strict=True)
                   if i.cuenta and dia_de_lima(m) == hoy]
        return len(del_dia), sum(i.tokens for i in del_dia)

    def medias_de_tokens(self) -> dict[str, float]:
        por_proposito: dict[str, list[int]] = {}
        for _, i in self.filas:
            if i.outcome == "ok" and i.purpose != SIN_TOPE:
                por_proposito.setdefault(i.purpose, []).append(i.tokens)
        return {p: sum(t) / len(t) for p, t in por_proposito.items()}


class RegistroPostgres:
    """Una fila de `llm_usage` por intento; los topes, de `llm_budget_settings`.
    Conexión corta por operación: son pocas y el proveedor corre en hilos distintos."""

    def __init__(self, dsn: str, tenant_id: str | None = None) -> None:
        from core.storage.postgres_store import DEFAULT_TENANT_ID

        self._dsn = dsn
        self._tenant = tenant_id or DEFAULT_TENANT_ID

    def guardar(self, run_id: str | None, intento: Intento) -> int:
        import psycopg

        with psycopg.connect(self._dsn) as conn:
            fila = conn.execute(
                "INSERT INTO radar.llm_usage (tenant_id, run_id, model, purpose, outcome, error_code, "
                "input_tokens, output_tokens, thinking_tokens) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING id",
                (self._tenant, run_id, intento.model, intento.purpose, intento.outcome, intento.error_code,
                 intento.input_tokens, intento.output_tokens, intento.thinking_tokens)).fetchone()
        assert fila is not None  # RETURNING de un INSERT siempre devuelve la fila
        return int(fila[0])

    def reasignar(self, ids: list[int], run_id: str) -> None:
        import psycopg

        with psycopg.connect(self._dsn) as conn:
            conn.execute("UPDATE radar.llm_usage SET run_id = %s WHERE tenant_id = %s AND id = ANY(%s)",
                         (run_id, self._tenant, ids))

    def topes(self) -> Topes:
        import psycopg

        with psycopg.connect(self._dsn) as conn:
            fila = conn.execute(
                "SELECT scan_max_calls, scan_max_tokens, daily_max_calls, daily_max_tokens "
                "FROM radar.llm_budget_settings WHERE tenant_id = %s", (self._tenant,)).fetchone()
        return Topes(*fila) if fila else TOPES_POR_DEFECTO

    def uso_de_hoy(self, ahora: datetime) -> tuple[int, int]:
        import psycopg

        with psycopg.connect(self._dsn) as conn:
            fila = conn.execute(
                "SELECT count(*), coalesce(sum(coalesce(input_tokens, 0) + coalesce(output_tokens, 0) "
                "+ coalesce(thinking_tokens, 0)), 0) FROM radar.llm_usage "
                "WHERE tenant_id = %s AND outcome <> 'cortada' AND purpose <> %s "
                "AND (created_at AT TIME ZONE 'America/Lima')::date = (%s::timestamptz AT TIME ZONE 'America/Lima')::date",
                (self._tenant, SIN_TOPE, ahora)).fetchone()
        return (int(fila[0]), int(fila[1])) if fila else (0, 0)

    def medias_de_tokens(self) -> dict[str, float]:
        import psycopg

        with psycopg.connect(self._dsn) as conn:
            filas = conn.execute(
                "SELECT purpose, avg(coalesce(input_tokens, 0) + coalesce(output_tokens, 0) "
                "+ coalesce(thinking_tokens, 0)) FROM radar.llm_usage "
                "WHERE tenant_id = %s AND outcome = 'ok' AND purpose <> %s GROUP BY purpose",
                (self._tenant, SIN_TOPE)).fetchall()
        return {str(p): float(m) for p, m in filas}

    def guardar_topes(self, topes: Topes) -> None:
        import psycopg

        with psycopg.connect(self._dsn) as conn:
            conn.execute(
                "INSERT INTO radar.llm_budget_settings (tenant_id, scan_max_calls, scan_max_tokens, "
                "daily_max_calls, daily_max_tokens) VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (tenant_id) DO UPDATE SET scan_max_calls = EXCLUDED.scan_max_calls, "
                "scan_max_tokens = EXCLUDED.scan_max_tokens, daily_max_calls = EXCLUDED.daily_max_calls, "
                "daily_max_tokens = EXCLUDED.daily_max_tokens, updated_at = now()",
                (self._tenant, *topes))
