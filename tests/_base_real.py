"""
Red de seguridad: los tests no llegan a la base real
====================================================

Se instala al importar el paquete `tests` (tests/__init__.py). Dos capas:

1. RIR_PG_URL apunta a una base de prueba que no existe: todo lo que
   resuelve el DSN por defecto (resolver_dsn) acaba ahí y falla.
2. `psycopg.connect`, `Connection.connect` y `AsyncConnection.connect`
   rechazan cualquier conexión a `reddit_intelligence_radar`, venga del
   camino que venga, antes de llegar al servidor.

La prueba de humo lee la base real en solo lectura: la libera con
`liberar_para_el_humo()` al empezar.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

from core.storage.postgres_store import DSN_ENV_VAR, DSN_ENV_VAR_ANTIGUA

BASE_REAL = "reddit_intelligence_radar"
BASE_DE_LOS_TESTS = "rir_base_real_prohibida_test"
_VARIABLES = (DSN_ENV_VAR, DSN_ENV_VAR_ANTIGUA)

_originales: dict[str, Any] = {}
_entorno: dict[str, str | None] = {}


def es_la_base_real(conninfo: str = "", **kwargs: Any) -> bool:
    from psycopg.conninfo import conninfo_to_dict

    return conninfo_to_dict(conninfo, **kwargs).get("dbname") == BASE_REAL


def _prohibida() -> AssertionError:
    return AssertionError(
        f"Base real prohibida en los tests: nada puede conectar a {BASE_REAL}. "
        "Usa una base desechable (tests/_postgres.py) o un doble.")


def dsn_de_los_tests() -> str:
    from core.rutas import ruta_pgpass

    return (f"postgresql://sentra_pruebas@localhost:5432/{BASE_DE_LOS_TESTS}"
            f"?passfile={quote(str(ruta_pgpass()), safe='')}")


def proteger() -> None:
    """Instala las dos capas. Idempotente."""
    import psycopg

    if getattr(psycopg.connect, "_guardia_de_la_base_real", False):
        return
    for variable in _VARIABLES:
        _entorno[variable] = os.environ.get(variable)
    os.environ.pop(DSN_ENV_VAR_ANTIGUA, None)
    os.environ[DSN_ENV_VAR] = dsn_de_los_tests()

    _originales.update(connect=psycopg.connect, sync=psycopg.Connection.connect,
                       asincrona=psycopg.AsyncConnection.connect)
    original_sync = _originales["sync"].__func__
    original_async = _originales["asincrona"].__func__

    def sync(cls: Any, conninfo: str = "", **kwargs: Any) -> Any:
        if es_la_base_real(conninfo, **kwargs):
            raise _prohibida()
        return original_sync(cls, conninfo, **kwargs)

    async def asincrona(cls: Any, conninfo: str = "", **kwargs: Any) -> Any:
        if es_la_base_real(conninfo, **kwargs):
            raise _prohibida()
        return await original_async(cls, conninfo, **kwargs)

    def conectar(conninfo: str = "", **kwargs: Any) -> Any:
        return psycopg.Connection.connect(conninfo, **kwargs)

    conectar._guardia_de_la_base_real = True  # type: ignore[attr-defined]
    psycopg.Connection.connect = classmethod(sync)  # type: ignore[method-assign, assignment]
    psycopg.AsyncConnection.connect = classmethod(asincrona)  # type: ignore[method-assign, assignment]
    psycopg.connect = conectar


def liberar_para_el_humo() -> None:
    """Quita las dos capas: la prueba de humo compara la app con la base real."""
    import psycopg

    if not getattr(psycopg.connect, "_guardia_de_la_base_real", False):
        return
    psycopg.connect = _originales["connect"]
    psycopg.Connection.connect = _originales["sync"]  # type: ignore[method-assign]
    psycopg.AsyncConnection.connect = _originales["asincrona"]  # type: ignore[method-assign]
    for variable, valor in _entorno.items():
        if valor is None:
            os.environ.pop(variable, None)
        else:
            os.environ[variable] = valor
