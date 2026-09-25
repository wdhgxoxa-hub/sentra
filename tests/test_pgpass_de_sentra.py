"""
SENTRA se conecta con su propio rol y su propio pgpass.conf
===========================================================

El 2026-09-24, a mitad de una compuerta, otro proyecto reescribió el
`%APPDATA%\\postgresql\\pgpass.conf` compartido y quitó la línea de
`postgres`: 44 tests y el humo cayeron sin que SENTRA cambiara nada. Y Rust
tomaba la primera línea de localhost fuera del usuario que fuera (habría
entrado como `faceless`). Decisión de Walter: rol `sentra_owner` para la
app, `sentra_pruebas` (CREATEDB) para las bases desechables de los tests, y
un pgpass propio en `%LOCALAPPDATA%\\SENTRA\\pgpass.conf`.
"""

import os
import re
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, unquote, urlsplit

RAIZ = Path(__file__).resolve().parents[1]


def sin_dsn_en_el_entorno():
    from core.storage.postgres_store import DSN_ENV_VAR, DSN_ENV_VAR_ANTIGUA

    limpio = {k: v for k, v in os.environ.items() if k not in (DSN_ENV_VAR, DSN_ENV_VAR_ANTIGUA)}
    return mock.patch.dict(os.environ, limpio, clear=True)


class TestRuta(unittest.TestCase):
    def test_el_pgpass_vive_en_la_carpeta_local_de_sentra(self):
        from core.rutas import carpeta_local, ruta_pgpass

        self.assertEqual(ruta_pgpass(), carpeta_local() / "pgpass.conf")


class TestDsnDeLaApp(unittest.TestCase):
    def test_por_defecto_entra_como_sentra_owner_con_su_pgpass(self):
        from core.rutas import ruta_pgpass
        from core.storage.postgres_store import resolver_dsn

        with sin_dsn_en_el_entorno():
            partes = urlsplit(resolver_dsn())
        self.assertEqual((partes.username, partes.hostname, partes.path),
                         ("sentra_owner", "localhost", "/reddit_intelligence_radar"))
        self.assertEqual([unquote(v) for v in parse_qs(partes.query)["passfile"]], [str(ruta_pgpass())])

    def test_un_dsn_explicito_o_del_entorno_no_se_toca(self):
        from core.storage.postgres_store import resolver_dsn

        with sin_dsn_en_el_entorno():
            self.assertEqual(resolver_dsn("postgresql://x@h/b"), "postgresql://x@h/b")
        with mock.patch.dict(os.environ, {"RIR_PG_URL": "postgresql://y@h/b"}):
            self.assertEqual(resolver_dsn(), "postgresql://y@h/b")


class TestDsnDeLosTests(unittest.TestCase):
    def test_las_bases_desechables_las_crea_sentra_pruebas_con_su_pgpass(self):
        from core.rutas import ruta_pgpass
        from tests._postgres import dsn_de_administracion

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RIR_PG_ADMIN_DSN", None)
            dsn = dsn_de_administracion()
        self.assertIn("user=sentra_pruebas", dsn)
        self.assertIn("dbname=postgres", dsn)
        ruta = str(ruta_pgpass()).replace("\\", "\\\\")
        self.assertIn(f"passfile='{ruta}'", dsn)


class TestNadieLeeElPgpassCompartido(unittest.TestCase):
    """Solo scripts/rol_sentra.py habla con el compartido (lo lee libpq para
    entrar como postgres una vez); nadie más lo nombra."""

    COMPARTIDO = re.compile(r"postgresql[\\/]+pgpass|join\(\"postgresql\"\)|\"postgresql\"\)\s*\.join", re.IGNORECASE)

    def test_ningun_codigo_nombra_el_pgpass_compartido(self):
        culpables = []
        for carpeta, sufijos in (("core", (".py",)), ("scripts", (".py",)), ("tests", (".py",)),
                                 ("ui/src-tauri/src", (".rs",))):
            for p in (RAIZ / carpeta).rglob("*"):
                if p.suffix not in sufijos or p.name in ("rol_sentra.py", Path(__file__).name):
                    continue
                if self.COMPARTIDO.search(p.read_text("utf-8")):
                    culpables.append(p.relative_to(RAIZ).as_posix())
        self.assertEqual(culpables, [])


if __name__ == "__main__":
    unittest.main()
