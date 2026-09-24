"""
Una sola variable y una sola resolución para la base (AUD2-011)
==============================================================

Rust leía RIR_PG_URL y Python RIR_PG_DSN: con una puesta solo la mitad de
la aplicación iba a otra base, y el aviso «sin base» nombraba solo una. Y la
misma resolución estaba repetida en once sitios. Ahora: RIR_PG_URL (URL,
que entienden sqlx y psycopg) en los dos lados; RIR_PG_DSN se acepta un
tiempo con aviso; el valor por defecto es el mismo en Rust y en Python; y
solo core.storage.postgres_store.resolver_dsn resuelve.
"""

import logging
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from core.storage.postgres_store import DEFAULT_DSN, resolver_dsn

RAIZ = Path(__file__).resolve().parents[1]


class TestResolverDsn(unittest.TestCase):
    def entorno(self, **valores):
        limpio = {k: v for k, v in os.environ.items() if k not in ("RIR_PG_URL", "RIR_PG_DSN")}
        return mock.patch.dict(os.environ, {**limpio, **valores}, clear=True)

    def test_precedencia(self):
        with self.entorno(RIR_PG_URL="postgresql://a@h/b", RIR_PG_DSN="host=x"):
            self.assertEqual(resolver_dsn("postgresql://explicito@h/b"), "postgresql://explicito@h/b")
            self.assertEqual(resolver_dsn(), "postgresql://a@h/b")
        with self.entorno():
            self.assertEqual(resolver_dsn(), DEFAULT_DSN)

    def test_la_variable_antigua_vale_con_aviso(self):
        with self.entorno(RIR_PG_DSN="host=antigua"), self.assertLogs("core.storage.postgres_store", logging.WARNING):
            self.assertEqual(resolver_dsn(), "host=antigua")

    def test_el_valor_por_defecto_es_el_de_rust(self):
        db_rs = (RAIZ / "ui" / "src-tauri" / "src" / "db.rs").read_text("utf-8")
        rust = re.search(r'const DEFAULT_DSN: &str =\s*"([^"]+)"', db_rs)
        assert rust is not None
        self.assertEqual(DEFAULT_DSN.replace("postgresql://", "postgres://"), rust.group(1))
        self.assertIn('DSN_ENV_VAR: &str = "RIR_PG_URL"', db_rs)

    def test_nadie_mas_resuelve_la_base(self):
        culpables = []
        for carpeta in ("core", "scripts", "tests"):
            for p in (RAIZ / carpeta).rglob("*.py"):
                if p.name in ("postgres_store.py", "test_dsn_unico.py"):
                    continue
                texto = p.read_text("utf-8")
                if re.search(r"os\.environ\.get\(DSN_ENV_VAR\)|or DEFAULT_DSN\b|RIR_PG_DSN", texto):
                    culpables.append(p.relative_to(RAIZ).as_posix())
        self.assertEqual(culpables, [])


if __name__ == "__main__":
    unittest.main()
