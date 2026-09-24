"""
Reddit se identifica y no se finge navegador (AUD-014)
=====================================================

Antes el cliente usaba curl_cffi con `impersonate="chrome124"` y el módulo
bypass.py añadía cookies (over18, _options, loid) y cabeceras Sec-Fetch-*
de navegador. Reddit exige lo contrario: un User-Agent que identifique la
aplicación y a su autor, con el formato

    <plataforma>:<app>:<versión> (by /u/<usuario>)

El cliente de ingesta se retiró con las demostraciones (D-C7). Queda lo que
reutiliza el adaptador de Reddit: la validación del User-Agent, con su error
tipado y traducido, y el guardia de que no vuelva nada de suplantación.
"""

import importlib
import re
import unittest
from pathlib import Path

from core.ingestion.errors import RedditUserAgentInvalid
from core.ingestion.user_agent import validar_user_agent
from tests._ayudas import presente

RAIZ = Path(__file__).resolve().parents[1]

#: User-Agent con el formato que exige Reddit.
UA = "python:sentra-tests:1.0 (by /u/sentra_ci)"


class TestSinSuplantacion(unittest.TestCase):

    def test_no_queda_ni_bypass_ni_impersonate_ni_curl_cffi(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("core.ingestion.bypass")
        for fichero in (RAIZ / "core").rglob("*.py"):
            texto = fichero.read_text(encoding="utf-8")
            with self.subTest(fichero=fichero.name):
                self.assertNotRegex(texto, r"impersonate|curl_cffi|over18|Sec-Fetch")
        self.assertNotRegex((RAIZ / "requirements.txt").read_text(encoding="utf-8"), "curl_cffi")


class TestUserAgent(unittest.TestCase):

    def test_un_user_agent_con_el_formato_de_reddit_es_valido(self):
        for bueno in (UA, "windows:sentra:0.9.2 (by /u/Alguien_Real)"):
            self.assertEqual(validar_user_agent(bueno), bueno)

    def test_el_valor_de_relleno_se_rechaza(self):
        for relleno in ("python:sentra:1.0 (by /u/tu_usuario)",
                        "python:sentra:1.0 (by /u/your_username)",
                        "python:sentra:1.0 (by /u/unknown)"):
            with self.assertRaises(RedditUserAgentInvalid) as ctx:
                validar_user_agent(relleno)
            self.assertEqual(ctx.exception.code, "reddit_user_agent_invalid")

    def test_formatos_que_no_identifican_se_rechazan(self):
        for malo in ("", "   ", "ua", "radar/1.0", "python:sentra:1.0",
                     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"):
            with self.subTest(ua=malo), self.assertRaises(RedditUserAgentInvalid):
                validar_user_agent(malo)

    def test_el_codigo_tiene_texto_en_es_y_en(self):
        for idioma in ("es", "en"):
            fuente = (RAIZ / "ui" / "src" / "i18n" / f"{idioma}.ts").read_text(encoding="utf-8")
            for bloque in ("errors",):
                encontrado = re.search(rf"\n  {bloque}: \{{(.*?)\n  \}},", fuente, re.DOTALL)
                self.assertIsNotNone(encontrado, (idioma, bloque))
                self.assertIn("reddit_user_agent_invalid:", presente(encontrado).group(1), (idioma, bloque))


if __name__ == "__main__":
    unittest.main()
