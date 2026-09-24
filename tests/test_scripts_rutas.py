"""
Rutas de los scripts (D5)
=========================

Los scripts escribían en `F:\\reddit_intelligence_radar\\...` fijo: fuera de
esa unidad fallaban o, peor, escribían en otra copia. Ahora cada script
resuelve sus rutas desde su propia ubicación. (Lo que vigilaba de las salidas
de la biblioteca de clones se fue con esos scripts; ver docs/historico.)
"""

import ast
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
UNIDAD = re.compile(r"^[A-Za-z]:[\\/]")


class TestRutasRelativas(unittest.TestCase):
    def test_ningun_script_fija_una_unidad_de_disco(self):
        absolutas = []
        for script in sorted((RAIZ / "scripts").glob("*.py")):
            for nodo in ast.walk(ast.parse(script.read_text(encoding="utf-8"))):
                if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) \
                        and UNIDAD.match(nodo.value):
                    absolutas.append(f"{script.name}:{nodo.lineno}")
        self.assertEqual(absolutas, [])


if __name__ == "__main__":
    unittest.main()
