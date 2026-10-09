"""
La ventana principal la crea `setup`, no tauri.conf.json (humo en Linux)
=======================================================================

En Linux la prueba de humo no tiene WEBVIEW2_USER_DATA_FOLDER: el perfil
aislado de WebKit llega con SENTRA_PERFIL_WEBVIEW y solo se puede fijar al
construir la ventana. Por eso tauri.conf.json la describe pero no la crea
(`create: false`) y `setup` la construye con `from_config`. Si la
configuración volviera a crearla, habría dos ventanas «main» y la app no
arrancaría.
"""

import json
import unittest
from pathlib import Path

TAURI = Path(__file__).resolve().parents[1] / "ui" / "src-tauri"


class TestVentanaPrincipal(unittest.TestCase):
    def test_la_configuracion_describe_la_ventana_pero_no_la_crea(self):
        ventanas = json.loads((TAURI / "tauri.conf.json").read_text("utf-8"))["app"]["windows"]
        self.assertEqual(len(ventanas), 1)
        self.assertIs(ventanas[0].get("create"), False)

    def test_setup_la_construye_con_el_perfil_del_humo(self):
        lib = (TAURI / "src" / "lib.rs").read_text("utf-8")
        self.assertIn("WebviewWindowBuilder::from_config", lib)
        self.assertIn("ventana::PERFIL_ENV_VAR", lib)


if __name__ == "__main__":
    unittest.main()
