"""
Una sola forma de saber si hay PostgreSQL en los tests (D3)
===========================================================

Cada suite tenía su copia de `_postgres_available` y de `ADMIN_DSN`; una
copia que se desfasa (otro DSN, otro timeout, un `except` distinto) hace que
una suite se salte en silencio mientras otra corre. Viven en
`tests/_postgres.py` y se importan de ahí.
"""

import ast
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent


class TestUnaSolaComprobacion(unittest.TestCase):
    def test_ninguna_suite_define_su_propia_comprobacion_ni_su_dsn(self):
        copias = []
        for fichero in sorted(TESTS.glob("test_*.py")):
            for nodo in ast.walk(ast.parse(fichero.read_text(encoding="utf-8"))):
                if isinstance(nodo, ast.FunctionDef) and nodo.name in (
                        "_postgres_available", "postgres_available"):
                    copias.append(f"{fichero.name}:{nodo.lineno} {nodo.name}")
                if isinstance(nodo, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id in ("ADMIN_DSN", "POSTGRES_AVAILABLE")
                        for t in nodo.targets):
                    copias.append(f"{fichero.name}:{nodo.lineno} asignación")
        self.assertEqual(copias, [])

    def test_la_comprobacion_compartida_se_calcula_una_vez(self):
        from tests import _postgres

        self.assertIs(_postgres.postgres_available(), _postgres.postgres_available())
        self.assertTrue(hasattr(_postgres.postgres_available, "cache_info"))


if __name__ == "__main__":
    unittest.main()
