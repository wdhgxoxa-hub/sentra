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


class TestValoresQueNoInyectan(unittest.TestCase):
    """AUD-036: un valor no puede añadir líneas al .env ni volver distinto."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rir_env_valores_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = self.tmp / ".env"
        self.env.write_text("A=1\n", encoding="utf-8")

    def test_un_salto_de_linea_en_el_valor_se_rechaza_sin_tocar_el_archivo(self):
        from core.envfile import EnvValueInvalid

        for malo in ("clave\nRIR_OTRA=inyectada", "clave\rX=1", "nul\x00"):
            with self.subTest(valor=repr(malo)), self.assertRaises(EnvValueInvalid) as caso:
                update_dotenv({"RIR_X": malo}, str(self.env))
            self.assertEqual(caso.exception.code, "env_value_invalid")
        self.assertEqual(self.env.read_text(encoding="utf-8"), "A=1\n")

    def test_una_clave_que_no_es_un_nombre_de_variable_se_rechaza(self):
        from core.envfile import EnvValueInvalid

        for mala in ("", "CON ESPACIO", "A=B", "1EMPIEZA", "#COMENTARIO"):
            with self.subTest(clave=mala), self.assertRaises(EnvValueInvalid):
                update_dotenv({mala: "x"}, str(self.env))

    def test_lo_escrito_vuelve_igual_al_leerlo(self):
        from core.ingestion.auth import load_dotenv

        valores = {"RIR_ESPACIOS": "  con espacios  ", "RIR_COMILLAS": '"entre comillas"',
                   "RIR_SIMPLES": "'simples'", "RIR_NORMAL": "abc=def#ghi"}
        update_dotenv(valores, str(self.env))
        leido = load_dotenv(str(self.env), env={})
        self.assertEqual({k: leido[k] for k in valores}, valores)
        self.assertEqual(leido["A"], "1")


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
