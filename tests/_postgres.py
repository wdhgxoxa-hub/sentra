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
