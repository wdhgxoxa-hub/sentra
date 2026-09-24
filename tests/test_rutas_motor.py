"""
Código del motor y datos del proyecto, separados (AUD2-003, DP1 B)
=================================================================

La release lanza el motor desde una copia versionada de su código, fuera
del repositorio. Los datos (el `.env`, los vectores de LanceDB) siguen en la
carpeta del proyecto, compartidos: ninguna ruta de datos puede salir de
`__file__`, porque en la copia apuntaría dentro de ella y el motor
arrancaría sin clave y sin vectores. Una sola raíz de datos, `RIR_DATA_DIR`,
con la carpeta del código como valor por defecto (desarrollo y tests).
"""

import os
import unittest
from pathlib import Path
from unittest import mock

from core import rutas
from core.envfile import default_env_path
from core.ingestion.auth import load_dotenv
from core.storage.lancedb_store import resolve_db_path

RAIZ_CODIGO = Path(__file__).resolve().parents[1]


class TestRaizDeDatos(unittest.TestCase):
    def test_sin_variable_es_la_carpeta_del_codigo(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(rutas.DATA_DIR_ENV_VAR, None)
            self.assertEqual(rutas.raiz_datos(), RAIZ_CODIGO)
            self.assertEqual(Path(default_env_path()), RAIZ_CODIGO / ".env")

    def test_con_variable_el_env_y_los_vectores_salen_de_ella(self):
        otra = Path("F:/proyecto-de-prueba")
        with mock.patch.dict(os.environ, {rutas.DATA_DIR_ENV_VAR: str(otra)}):
            os.environ.pop("RIR_LANCEDB_PATH", None)
            self.assertEqual(rutas.raiz_datos(), otra)
            self.assertEqual(Path(default_env_path()), otra / ".env")
            self.assertEqual(resolve_db_path(), otra / "data" / "lancedb")

    def test_la_carga_de_credenciales_antigua_lee_el_mismo_env(self):
        leidos: list[str] = []

        def abrir(ruta: object, *_: object, **__: object) -> None:
            leidos.append(str(ruta))
            raise FileNotFoundError(ruta)

        with mock.patch.dict(os.environ, {rutas.DATA_DIR_ENV_VAR: "F:/proyecto-de-prueba"}), \
             mock.patch("builtins.open", side_effect=abrir):
            load_dotenv(env={})
        self.assertEqual([Path(r) for r in leidos], [Path("F:/proyecto-de-prueba/.env")])

    def test_ninguna_ruta_de_datos_sale_de_file(self):
        """Solo el propio código (fuentes del PDF) puede ubicarse con __file__."""
        permitidos = {"core/rutas.py", "core/documents/pdf_report.py"}
        culpables = []
        for fichero in (RAIZ_CODIGO / "core").rglob("*.py"):
            rel = fichero.relative_to(RAIZ_CODIGO).as_posix()
            if rel not in permitidos and "__file__" in fichero.read_text(encoding="utf-8"):
                culpables.append(rel)
        self.assertEqual(culpables, [])


if __name__ == "__main__":
    unittest.main()
