"""
Configuración de calidad del proyecto (AUD-023, AUD-024)
========================================================

Sin configuración, ruff y mypy aplicaban lo que trajera cada versión
instalada: el mismo código daba cifras distintas en cada máquina y "cero
avisos" no significaba nada. pyproject.toml fija la versión de ruff, el
Python de destino y el rigor de mypy sobre core/.
"""

import re
import tomllib
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PYPROJECT = RAIZ / "pyproject.toml"


def _version_fijada(paquete: str) -> str:
    texto = (RAIZ / "requirements-dev.txt").read_text(encoding="utf-8")
    encontrada = re.search(rf"^{paquete}==(\S+)", texto, re.MULTILINE)
    assert encontrada, f"{paquete} no está fijado en requirements-dev.txt"
    return encontrada.group(1)


class TestConfiguracionDeCalidad(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PYPROJECT.is_file(), "falta pyproject.toml")
        self.config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]

    def test_ruff_exige_la_version_fijada_en_requirements_dev(self):
        """Otra versión de ruff trae otro juego de reglas por defecto."""
        self.assertEqual(
            self.config["ruff"]["required-version"], f"=={_version_fijada('ruff')}"
        )

    def test_ruff_y_mypy_analizan_para_el_python_del_proyecto(self):
        self.assertEqual(self.config["ruff"]["target-version"], "py312")
        self.assertEqual(self.config["mypy"]["python_version"], "3.12")

    def test_mypy_revisa_todo_el_codigo_propio(self):
        self.assertEqual(set(self.config["mypy"]["files"]), {"core", "scripts", "tests"})
        self.assertTrue(self.config["mypy"]["strict_optional"])

    def test_core_no_admite_funciones_sin_tipar(self):
        overrides = self.config["mypy"]["overrides"]
        core = [o for o in overrides if o.get("module") == "core.*"]
        self.assertEqual(len(core), 1, overrides)
        self.assertTrue(core[0]["disallow_untyped_defs"])

    def test_los_scripts_se_revisan_aunque_no_esten_anotados(self):
        """Sin esto mypy no mira el cuerpo de las funciones sin anotar, y un
        script que llamaba al cliente con un argumento que ya no existe
        pasaba limpio (AUD-014)."""
        overrides = self.config["mypy"]["overrides"]
        scripts = [o for o in overrides if o.get("module") == "scripts.*"]
        self.assertEqual(len(scripts), 1, overrides)
        self.assertTrue(scripts[0]["check_untyped_defs"])


if __name__ == "__main__":
    unittest.main()
