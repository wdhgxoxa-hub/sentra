"""
scripts/migrate.py como programa (AUD2-011)
==========================================

Al unificar la resolución de la base, `python scripts/migrate.py status`
dejó de arrancar: importaba `core` antes de poner la raíz del proyecto en la
ruta (ModuleNotFoundError). Los tests importaban el módulo desde la raíz y
no lo veían; este lo lanza como lo lanza el usuario. Además, con la URL
como forma canónica, el informe tiene que ocultar también la contraseña de
una URL, no solo la de `password=`.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

from core.storage.postgres_store import DSN_ENV_VAR, DSN_ENV_VAR_ANTIGUA
from scripts.migrate import _redact

RAIZ = Path(__file__).resolve().parents[1]


class TestMigrateComoPrograma(unittest.TestCase):
    def test_arranca_fuera_del_repo_y_falla_por_la_base_no_por_la_ruta(self):
        entorno = {k: v for k, v in os.environ.items() if k not in (DSN_ENV_VAR_ANTIGUA, "PYTHONPATH")}
        entorno[DSN_ENV_VAR] = "postgresql://nadie@127.0.0.1:1/nada?connect_timeout=2"
        salida = subprocess.run([sys.executable, str(RAIZ / "scripts" / "migrate.py"), "status"],
                                capture_output=True, text=True, cwd=Path.home(), env=entorno,
                                timeout=60, check=False)
        todo = salida.stdout + salida.stderr
        self.assertNotIn("ModuleNotFoundError", todo)
        self.assertNotEqual(salida.returncode, 0, "sin base no puede decir que todo va bien")


class TestRedact(unittest.TestCase):
    def test_oculta_la_contrasena_en_las_dos_formas(self):
        self.assertEqual(_redact("host=h user=u password=secreta dbname=d"),
                         "host=h user=u password=*** dbname=d")
        self.assertEqual(_redact("postgresql://u:secreta@h:5432/d"), "postgresql://u:***@h:5432/d")
        self.assertEqual(_redact("postgresql://u@h/d"), "postgresql://u@h/d")


if __name__ == "__main__":
    unittest.main()
