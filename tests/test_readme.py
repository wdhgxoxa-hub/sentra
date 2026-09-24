"""
El README existe y no se desfasa de lo que dice (AUD-052, D-C8)
===============================================================

Sin CI remota, el README es donde se explica la compuerta local. Se
comprueba que exista y que lo que nombra (scripts, documentos) siga
existiendo.
"""

import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


class TestReadme(unittest.TestCase):
    def test_existe_y_explica_la_compuerta(self):
        texto = (RAIZ / "README.md").read_text(encoding="utf-8")
        for orden in ("ruff check", "mypy", "unittest discover", "tsc --noEmit", "cargo test",
                      "cargo clippy --all-targets -- -D warnings", "migrate.py up --dry-run"):
            self.assertIn(orden, texto)

    def test_las_rutas_que_cita_existen(self):
        texto = (RAIZ / "README.md").read_text(encoding="utf-8")
        citadas = set(re.findall(r"`((?:scripts|docs|tasks|tests|sql|ui)[/\][\w./\-]+)`", texto))
        self.assertTrue(citadas)
        faltan = sorted(r for r in citadas if not (RAIZ / r.replace("\\", "/")).exists())
        self.assertEqual(faltan, [])


if __name__ == "__main__":
    unittest.main()
