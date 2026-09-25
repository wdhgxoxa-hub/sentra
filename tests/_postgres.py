"""
PostgreSQL de los tests (D3)
============================

Una sola forma de saber si hay servidor y con qué DSN de administración se
crean las bases desechables. Se calcula una vez por proceso: antes cada
suite abría su propia conexión de prueba, con su propio DSN y su propio
manejo de errores (tests/test_postgres_compartido.py lo vigila).
"""

import functools
import os
import re

ADMIN_DSN = os.environ.get(
    "RIR_PG_ADMIN_DSN", "host=localhost port=5432 user=postgres dbname=postgres"
)


@functools.cache
def postgres_available() -> bool:
    """True si hay psycopg y el servidor acepta la conexión de administración."""
    try:
        import psycopg
    except ImportError:
        return False
    try:
        with psycopg.connect(ADMIN_DSN, connect_timeout=3):
            return True
    except psycopg.Error:
        return False


#: Solo las bases desechables de los tests: nunca la real ni las de otro proyecto.
_DESECHABLE = re.compile(r"rir_\w+_test")


def borrar_base_de_prueba(nombre: str) -> None:
    """Borra una base desechable sin la opción FORCE de DROP DATABASE.

    FORCE intenta terminar todo proceso de la base, también un autovacuum, y
    un rol sin superusuario no puede (cazado el 2026-09-24 con sentra_pruebas).
    Sin FORCE el servidor cancela el autovacuum él solo; las sesiones del
    propio rol que se hayan quedado abiertas se cierran antes.
    """
    if not _DESECHABLE.fullmatch(nombre):
        raise ValueError(f"{nombre!r} no es una base desechable de los tests (rir_*_test)")
    import psycopg
    from psycopg import sql

    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                     "WHERE datname = %s AND usename = current_user AND pid <> pg_backend_pid()", (nombre,))
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(nombre)))
