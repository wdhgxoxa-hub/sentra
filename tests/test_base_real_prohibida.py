"""
Ningún test llega a la base real
================================

El 2026-09-25 la suite escribió 25 filas falsas en el llm_usage de la base
real: un camino nuevo (el registro de uso del listado de modelos) resolvía el
DSN por defecto y nadie lo cortaba. `prohibir_red_real` corta caminos uno a
uno; esta red los corta todos (decisión de Walter): durante los tests
RIR_PG_URL apunta a una base que no existe y cualquier conexión a
`reddit_intelligence_radar`, venga de donde venga, falla sin llegar al
servidor. Solo la prueba de humo, que la lee en solo lectura, la libera.
"""

import asyncio
import os
import unittest

import psycopg

from tests import _base_real

REAL = "postgresql://sentra_owner@localhost:5432/reddit_intelligence_radar"


class TestRedDeSeguridad(unittest.TestCase):
    def test_el_dsn_de_los_tests_no_es_la_base_real(self):
        from core.storage.postgres_store import resolver_dsn

        dsn = resolver_dsn()
        self.assertNotIn(_base_real.BASE_REAL, dsn)
        self.assertEqual(os.environ["RIR_PG_URL"], dsn)

    def test_conectar_a_la_base_real_falla_venga_de_donde_venga(self):
        for conectar in (lambda: psycopg.connect(REAL),
                         lambda: psycopg.Connection.connect(REAL),
                         lambda: psycopg.connect("host=localhost dbname=reddit_intelligence_radar"),
                         lambda: psycopg.connect("host=localhost", dbname="reddit_intelligence_radar"),
                         lambda: asyncio.run(psycopg.AsyncConnection.connect(REAL),
                                             loop_factory=asyncio.SelectorEventLoop)):
            with self.subTest(), self.assertRaisesRegex(AssertionError, "Base real prohibida en los tests"):
                conectar()

    def test_otras_bases_siguen_abiertas(self):
        self.assertFalse(_base_real.es_la_base_real("host=localhost dbname=postgres"))
        self.assertFalse(_base_real.es_la_base_real("postgresql://x@localhost/rir_algo_test"))

    def test_el_humo_la_libera_y_se_puede_volver_a_proteger(self):
        self.addCleanup(_base_real.proteger)
        antes = os.environ.get("RIR_PG_URL")
        _base_real.liberar_para_el_humo()
        self.assertNotEqual(os.environ.get("RIR_PG_URL"), antes)
        self.assertFalse(getattr(psycopg.connect, "_guardia_de_la_base_real", False))
        _base_real.proteger()
        self.assertTrue(getattr(psycopg.connect, "_guardia_de_la_base_real", False))


if __name__ == "__main__":
    unittest.main()
