"""
Escritura atómica del .env (F2, R6)
===================================

El .env guarda las claves de todas las fuentes. Se escribe entero a un
archivo temporal de la misma carpeta y se sustituye de golpe (os.replace):
si el proceso muere a mitad, queda el archivo anterior intacto, nunca uno
truncado sin claves.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.envfile import update_dotenv


class TestEscrituraAtomica(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rir_env_atomico_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = self.tmp / ".env"
        self.env.write_text("# comentario\nA=1\nB=2\n", encoding="utf-8")

    def test_actualiza_conserva_y_anade(self):
        update_dotenv({"B": "20", "C": "3"}, str(self.env))
        self.assertEqual(self.env.read_text(encoding="utf-8"), "# comentario\nA=1\nB=20\nC=3\n")

    def test_si_falla_a_mitad_el_anterior_queda_intacto(self):
        antes = self.env.read_text(encoding="utf-8")
        with mock.patch("core.envfile.os.replace", side_effect=OSError("apagado")), \
                self.assertRaises(OSError):
            update_dotenv({"B": "20"}, str(self.env))
        self.assertEqual(self.env.read_text(encoding="utf-8"), antes)
        self.assertEqual([p.name for p in self.tmp.iterdir()], [".env"], "sin temporales huérfanos")

    def test_no_se_escribe_directamente_sobre_el_destino(self):
        escrito = []
        original = Path.write_text

        def espia(ruta, *args, **kwargs):
            escrito.append(Path(ruta).name)
            return original(ruta, *args, **kwargs)

        with mock.patch.object(Path, "write_text", espia):
            update_dotenv({"B": "20"}, str(self.env))
        self.assertNotIn(".env", escrito)

    def test_crea_el_archivo_si_no_existe(self):
        nuevo = self.tmp / "sub" / ".env"
        update_dotenv({"X": "1"}, str(nuevo))
        self.assertEqual(nuevo.read_text(encoding="utf-8"), "X=1\n")
        self.assertTrue(os.path.exists(nuevo))


if __name__ == "__main__":
    unittest.main()
