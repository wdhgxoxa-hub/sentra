"""
Huella del código del motor (AUD2-003, DP1 B)
============================================

La interfaz se compila con la huella del código del motor que empaqueta; el
motor calcula la de su propia copia y la devuelve en `/api/health`. Si no
coinciden, la interfaz lo dice con un código en lugar de hablar con un motor
de otro contrato (así nació la pantalla negra). Rust y Python calculan la
misma función: FNV-1a de 64 bits, comprobada aquí con los vectores
publicados (los mismos que comprueba el test de Rust) para que ninguna de
las dos implementaciones se pruebe solo contra sí misma.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import rutas
from tests.test_sidecar_config import ConfigTestCase


class TestFnv(unittest.TestCase):
    def test_vectores_publicados_de_fnv1a_64(self):
        self.assertEqual(rutas.fnv1a64(b""), "cbf29ce484222325")
        self.assertEqual(rutas.fnv1a64(b"a"), "af63dc4c8601ec8c")
        self.assertEqual(rutas.fnv1a64(b"foobar"), "85944171f73967e8")


class TestHuella(unittest.TestCase):
    def test_composicion_ruta_longitud_contenido_y_orden(self):
        esperada = rutas.fnv1a64(b"a.py\x001\x00x" + b"b/c.sql\x002\x00yz")
        self.assertEqual(rutas.huella([("b/c.sql", b"yz"), ("a.py", b"x")]), esperada)

    def test_cambiar_un_byte_cambia_la_huella(self):
        self.assertNotEqual(rutas.huella([("a.py", b"x")]), rutas.huella([("a.py", b"y")]))

    def test_la_huella_de_una_carpeta_ignora_la_cache_de_python_y_los_marcadores(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "core").mkdir()
            (raiz / "core" / "m.py").write_bytes(b"x = 1\n")
            limpia = rutas.huella_de_carpeta(raiz)
            (raiz / "core" / "__pycache__").mkdir()
            (raiz / "core" / "__pycache__" / "m.cpython-312.pyc").write_bytes(b"\x00")
            (raiz / ".completo").write_bytes(b"")
            self.assertEqual(rutas.huella_de_carpeta(raiz), limpia)
            self.assertEqual(limpia, rutas.huella([("core/m.py", b"x = 1\n")]))


class TestSalud(ConfigTestCase):
    def test_salud_dice_desde_donde_corre_el_motor(self):
        with mock.patch.dict(os.environ, {rutas.VERSIONADO_ENV_VAR: ""}):
            cuerpo = self.client.get("/api/health").json()
        self.assertEqual(cuerpo["codeRoot"], str(rutas.RAIZ_CODIGO))
        self.assertIsNone(cuerpo["build"], "desde el repo (desarrollo) no hay huella que comparar")

    def test_en_la_copia_versionada_devuelve_su_huella(self):
        with mock.patch.dict(os.environ, {rutas.VERSIONADO_ENV_VAR: "1"}), \
             mock.patch.object(rutas, "huella_de_carpeta", return_value="0123456789abcdef") as calcular:
            rutas.huella_del_motor.cache_clear()
            self.addCleanup(rutas.huella_del_motor.cache_clear)
            cuerpo = self.client.get("/api/health").json()
        self.assertEqual(cuerpo["build"], "0123456789abcdef")
        calcular.assert_called_once_with(rutas.RAIZ_CODIGO)


if __name__ == "__main__":
    unittest.main()
