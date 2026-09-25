"""
Punto único de control de Gemini (Fase 1, B4)
=============================================

Toda llamada a Gemini pasa por aquí: `GeminiProvider` no se crea sin un
`ControlDeGemini`. Antes de cada intento se comprueba el propósito (y, con
los topes, si puede salir); después, el intento queda como una fila de
`llm_usage` (migración 017): `ok` o `error` si salió, con sus tokens si el
proveedor los informó. Cada reintento es una llamada real y cuenta como tal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

#: Los mismos que el CHECK de llm_usage (sql/migrations/017_uso_y_topes_de_gemini.sql).
PROPOSITOS = frozenset({"etiquetado", "g0", "abogado", "dossier", "plan", "prueba_clave",
                        "listado_modelos", "otros"})
RESULTADOS = frozenset({"ok", "error", "cortada"})


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


class RegistroDeUso(Protocol):
    """Dónde queda cada intento. `guardar` devuelve el id de la fila."""

    def guardar(self, run_id: str | None, intento: Intento) -> int: ...

    def reasignar(self, ids: list[int], run_id: str) -> None: ...


class ControlDeGemini:
    """Lo que el proveedor consulta antes de cada intento y avisa después.

    `run_id` es la ejecución a la que se carga el uso; los documentos y el
    listado de modelos no son de ningún escaneo (None). El re-juicio llama a
    Gemini antes de crear su ejecución: `asignar_ejecucion` se la da también a
    lo ya anotado por este control.
    """

    def __init__(self, registro: RegistroDeUso, *, run_id: str | None = None) -> None:
        self._registro = registro
        self.run_id = run_id
        self._sin_ejecucion: list[int] = []

    def asignar_ejecucion(self, run_id: str) -> None:
        self.run_id = run_id
        if self._sin_ejecucion:
            self._registro.reasignar(self._sin_ejecucion, run_id)
            self._sin_ejecucion = []

    def antes(self, purpose: str) -> None:
        """Se llama antes de cada intento: un propósito desconocido no sale."""
        if purpose not in PROPOSITOS:
            raise ValueError(f"propósito de llamada desconocido: {purpose!r}")

    def anotar(self, intento: Intento) -> None:
        if intento.outcome not in RESULTADOS:
            raise ValueError(f"resultado desconocido: {intento.outcome!r}")
        fila = self._registro.guardar(self.run_id, intento)
        if self.run_id is None:
            self._sin_ejecucion.append(fila)


class RegistroEnMemoria:
    """Registro del motor sin persistencia (tests, demo sin base): los intentos
    quedan en `filas` como (run_id, Intento), en orden."""

    def __init__(self) -> None:
        self.filas: list[tuple[str | None, Intento]] = []

    def guardar(self, run_id: str | None, intento: Intento) -> int:
        self.filas.append((run_id, intento))
        return len(self.filas) - 1

    def reasignar(self, ids: list[int], run_id: str) -> None:
        for i in ids:
            self.filas[i] = (run_id, self.filas[i][1])


class RegistroPostgres:
    """Una fila de `llm_usage` por intento. Conexión corta por fila: son pocas
    y el proveedor corre en hilos distintos."""

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
