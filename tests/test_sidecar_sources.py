"""
Sección «Fuentes» del sidecar (F2.4, F2.8, R6)
==============================================

Estado verificado por fuente, credenciales guardadas con escritura atómica
(nunca devueltas), botón Probar con llamada mínima real, encendido/apagado
y modo comercial. Ningún test sale a la red: el cliente HTTP de las fuentes
es un doble.
"""

import unittest
from unittest import mock

import httpx

from tests.test_sidecar_config import ConfigTestCase


def hn_ok(_peticion):
    return httpx.Response(200, json={"hits": [], "nbHits": 123, "page": 0, "nbPages": 0})


def con_transporte(manejador):
    return mock.patch("core.sources.http.new_client",
                      lambda: httpx.AsyncClient(transport=httpx.MockTransport(manejador)))


class TestListado(ConfigTestCase):
    def test_hacker_news_aparece_publica_y_sin_verificar(self):
        cuerpo = self.client.get("/api/sources").json()
        self.assertFalse(cuerpo["commercialMode"])
        hn = next(s for s in cuerpo["sources"] if s["source"] == "hackernews")
        self.assertEqual(hn["status"], "configurada_sin_verificar")
        self.assertFalse(hn["requiresCredentials"])
        self.assertTrue(hn["termsUrl"].startswith("https://"))
        self.assertIsNone(hn["lastVerifiedAt"])


class TestProbar(ConfigTestCase):
    def test_una_respuesta_real_la_deja_verificada_con_hora(self):
        with con_transporte(hn_ok):
            probado = self.client.post("/api/sources/hackernews/probe").json()
        self.assertTrue(probado["ok"])
        hn = next(s for s in self.client.get("/api/sources").json()["sources"]
                  if s["source"] == "hackernews")
        self.assertEqual(hn["status"], "verificada")
        self.assertIsNotNone(hn["lastVerifiedAt"])

    def test_un_fallo_la_deja_en_error_con_codigo(self):
        with con_transporte(lambda _r: httpx.Response(503)):
            probado = self.client.post("/api/sources/hackernews/probe").json()
        self.assertFalse(probado["ok"])
        self.assertEqual(probado["code"], "source_unavailable")
        hn = next(s for s in self.client.get("/api/sources").json()["sources"]
                  if s["source"] == "hackernews")
        self.assertEqual((hn["status"], hn["errorCode"]), ("error", "source_unavailable"))

    def test_una_fuente_desconocida_es_404(self):
        self.assertEqual(self.client.post("/api/sources/inventada/probe").status_code, 404)


class TestEncendido(ConfigTestCase):
    def test_apagar_y_encender(self):
        self.client.post("/api/sources/hackernews/enabled", json={"enabled": False})
        hn = next(s for s in self.client.get("/api/sources").json()["sources"]
                  if s["source"] == "hackernews")
        self.assertEqual(hn["status"], "deshabilitada_por_usuario")
        self.client.post("/api/sources/hackernews/enabled", json={"enabled": True})
        hn = next(s for s in self.client.get("/api/sources").json()["sources"]
                  if s["source"] == "hackernews")
        self.assertEqual(hn["status"], "configurada_sin_verificar")


class TestModoComercial(ConfigTestCase):
    def test_se_guarda_y_se_informa(self):
        self.client.post("/api/sources/commercial-mode", json={"enabled": True})
        self.assertTrue(self.client.get("/api/sources").json()["commercialMode"])
        self.assertIn("RIR_COMMERCIAL_MODE=1", self.env_path.read_text(encoding="utf-8"))


class TestSinRed(unittest.TestCase):
    def test_la_guardia_de_los_tests_tambien_cubre_las_fuentes(self):
        from core.sources import http
        from tests._sin_red import prohibir_red_real

        prohibir_red_real(self)
        with self.assertRaises(AssertionError):
            http.new_client()


if __name__ == "__main__":
    unittest.main()
