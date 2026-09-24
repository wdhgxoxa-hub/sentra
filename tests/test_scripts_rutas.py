"""
Rutas de los scripts y lo que generan (D5)
==========================================

Los scripts escribían en `F:\\reddit_intelligence_radar\\...` fijo: fuera de
esa unidad fallaban o, peor, escribían en otra copia. Y lo que generaban
(INDEX.md, informes de demostración, auditorías) acababa versionado. Ahora
cada script resuelve sus rutas desde su propia ubicación, y todo lo generado
queda ignorado por git salvo `logs/repo_catalog.json`: es la entrada de
`clone_manager.py` y no se puede regenerar sin los clones.
"""

import ast
import re
import shutil
import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
UNIDAD = re.compile(r"^[A-Za-z]:[\\/]")

#: Lo que generan los scripts, relativo a la raíz del repositorio.
GENERADOS = (
    "INDEX.md",
    "logs/clone_results.json",
    "logs/integrity_audit.json",
    "logs/demo_scan_titles.md",
    "logs/demo_deep_dive.md",
    "logs/demo_intelligence_report.json",
    "logs/demo_intelligence_report.md",
)


class TestRutasRelativas(unittest.TestCase):
    def test_ningun_script_fija_una_unidad_de_disco(self):
        absolutas = []
        for script in sorted((RAIZ / "scripts").glob("*.py")):
            for nodo in ast.walk(ast.parse(script.read_text(encoding="utf-8"))):
                if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) \
                        and UNIDAD.match(nodo.value):
                    absolutas.append(f"{script.name}:{nodo.lineno}")
        self.assertEqual(absolutas, [])


@unittest.skipUnless(shutil.which("git") and (RAIZ / ".git").exists(), "sin git")
class TestNadaGeneradoSeVersiona(unittest.TestCase):
    def git(self, *args):
        return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True,
                              check=False)

    def test_lo_generado_esta_ignorado(self):
        no_ignorados = [r for r in GENERADOS if self.git("check-ignore", "-q", r).returncode != 0]
        self.assertEqual(no_ignorados, [])

    def test_lo_generado_no_esta_en_el_indice(self):
        versionados = self.git("ls-files", *GENERADOS).stdout.split()
        self.assertEqual(versionados, [])

    def test_el_catalogo_de_repos_si_se_versiona(self):
        self.assertEqual(self.git("ls-files", "logs/repo_catalog.json").stdout.strip(),
                         "logs/repo_catalog.json")


if __name__ == "__main__":
    unittest.main()
