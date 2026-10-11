"""
El puerto de PostgreSQL se elige con RIR_PG_PORT (fase 2, contenedores)
=======================================================================

La base de SENTRA pasa del Postgres nativo (5432) al contenedor `sentra-pg`
(127.0.0.1:5438). Mientras conviven, la app, el MCP y los tests tienen que
poder ir a uno u otro sin tocar el código. `RIR_PG_URL` no basta: sqlx (Rust)
no lee el pgpass, así que con una URL sin contraseña la ventana no entra.
`RIR_PG_PORT` solo cambia el puerto del DSN por defecto, y el pgpass de SENTRA
sigue dando la contraseña (libpq en Python; `contrasena_en_pgpass` en Rust,
que busca la línea de ese puerto). Sin la variable: 5432, como siempre.
"""

import os
import unittest
from unittest import mock
from urllib.parse import parse_qs, unquote, urlsplit

VARIABLE = "RIR_PG_PORT"


def entorno(**valores: str):
    """Entorno sin DSN explícitos y sin puerto, más `valores`."""
    from core.storage.postgres_store import DSN_ENV_VAR, DSN_ENV_VAR_ANTIGUA

    fuera = (DSN_ENV_VAR, DSN_ENV_VAR_ANTIGUA, "RIR_PG_ADMIN_DSN", VARIABLE)
    limpio = {k: v for k, v in os.environ.items() if k not in fuera}
    limpio.update(valores)
    return mock.patch.dict(os.environ, limpio, clear=True)


class TestPuertoDeLaApp(unittest.TestCase):
    def test_sin_variable_el_puerto_es_5432(self):
        from core.storage.postgres_store import puerto_pg, resolver_dsn

        with entorno():
            self.assertEqual(puerto_pg(), 5432)
            self.assertEqual(urlsplit(resolver_dsn()).port, 5432)

    def test_con_variable_cambia_solo_el_puerto_y_sigue_el_pgpass(self):
        from core.rutas import ruta_pgpass
        from core.storage.postgres_store import resolver_dsn

        with entorno(RIR_PG_PORT="5438"):
            partes = urlsplit(resolver_dsn())
        self.assertEqual((partes.username, partes.hostname, partes.port, partes.path),
                         ("sentra_owner", "localhost", 5438, "/reddit_intelligence_radar"))
        self.assertEqual([unquote(v) for v in parse_qs(partes.query)["passfile"]], [str(ruta_pgpass())])

    def test_un_dsn_explicito_gana_al_puerto(self):
        from core.storage.postgres_store import resolver_dsn

        with entorno(RIR_PG_PORT="5438", RIR_PG_URL="postgresql://y@h:1/b"):
            self.assertEqual(resolver_dsn(), "postgresql://y@h:1/b")

    def test_un_valor_que_no_es_puerto_se_ignora_con_aviso(self):
        from core.storage.postgres_store import puerto_pg

        for malo in ("abc", "0", "70000", "-5", "54 38"):
            with (self.subTest(malo=malo), entorno(RIR_PG_PORT=malo),
                  self.assertLogs("core.storage.postgres_store", level="WARNING")):
                self.assertEqual(puerto_pg(), 5432)

    def test_espacios_alrededor_no_molestan(self):
        from core.storage.postgres_store import puerto_pg

        with entorno(RIR_PG_PORT=" 5438 "):
            self.assertEqual(puerto_pg(), 5438)


class TestPuertoDeLosTests(unittest.TestCase):
    def test_las_bases_desechables_van_al_puerto_elegido(self):
        from tests._postgres import dsn_de_administracion

        with entorno():
            self.assertIn("port=5432", dsn_de_administracion())
        with entorno(RIR_PG_PORT="5438"):
            dsn = dsn_de_administracion()
        self.assertIn("port=5438", dsn)
        self.assertIn("user=sentra_pruebas", dsn)

    def test_la_base_prohibida_de_los_tests_va_al_puerto_elegido(self):
        from tests._base_real import BASE_DE_LOS_TESTS, dsn_de_los_tests

        with entorno(RIR_PG_PORT="5438"):
            partes = urlsplit(dsn_de_los_tests())
        self.assertEqual((partes.port, partes.path), (5438, f"/{BASE_DE_LOS_TESTS}"))


if __name__ == "__main__":
    unittest.main()
