"""
Cliente HTTP de las fuentes y secretos en los logs (R6)
=======================================================

Algunas APIs exigen la credencial en la URL (Stack Exchange: `key=`), y
httpx registra cada URL a nivel INFO, que es el nivel del sidecar. El filtro
de core/sources/http.py tapa esos parámetros antes de escribir nada.
"""

import logging
import unittest

import httpx

from core.sources import http as fuentes_http


class TestRedaccion(unittest.TestCase):
    def registrar(self, url):
        registros = []

        class Captura(logging.Handler):
            def emit(self, record):
                registros.append(record.getMessage())

        registro = logging.getLogger("httpx")
        captura = Captura()
        registro.addHandler(captura)
        nivel = registro.level
        registro.setLevel(logging.INFO)
        self.addCleanup(registro.removeHandler, captura)
        self.addCleanup(registro.setLevel, nivel)
        # La misma llamada que hace httpx al enviar una petición.
        registro.info('HTTP Request: %s %s "%s %d %s"', "GET", httpx.URL(url), "HTTP/1.1", 200, "OK")
        return registros[0]

    def test_la_clave_en_la_url_no_llega_al_log(self):
        linea = self.registrar(
            "https://api.stackexchange.com/2.3/info?site=stackoverflow&key=CLAVE-INVENTADA-123")
        self.assertNotIn("CLAVE-INVENTADA-123", linea)
        self.assertIn("key=***", linea)
        self.assertIn("site=stackoverflow", linea)

    def test_tambien_tokens_y_secretos(self):
        linea = self.registrar(
            "https://example.com/x?access_token=AAA111&client_secret=BBB222&token=CCC333&q=hola")
        for secreto in ("AAA111", "BBB222", "CCC333"):
            self.assertNotIn(secreto, linea)
        self.assertIn("q=hola", linea)

    def test_el_filtro_esta_instalado_al_importar_el_modulo(self):
        self.assertTrue(any(isinstance(f, fuentes_http.RedactSecrets)
                            for f in logging.getLogger("httpx").filters))


if __name__ == "__main__":
    unittest.main()
