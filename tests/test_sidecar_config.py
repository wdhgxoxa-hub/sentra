"""
Suite de configuración del sidecar
==================================

Cubre lo que la vista de Configuración necesita del backend: dónde está el
`.env` y el estado de Gemini (clave y modelos), sin abrir una terminal. El
cambio de fuente demo/Reddit, las credenciales de Reddit, el Blueprint, el
plan de arquitectura y la traducción se retiraron con la pipeline antigua
(C2): sus rutas ya no existen (tests/test_sidecar.py, TestSurface).

Ningún test escribe en el `.env` real ni sale a la red.
"""

import logging
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from core.orchestration.sidecar_server import create_app
from tests._sin_red import prohibir_red_real


def setUpModule():
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


class ConfigTestCase(unittest.TestCase):

    def setUp(self):
        prohibir_red_real(self)
        self.tmpdir = Path(tempfile.mkdtemp(prefix="rir_config_"))
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        self.env_path = self.tmpdir / ".env"
        self.app = create_app(insecure_dev=True, persist_default=False, env_path=str(self.env_path))
        self.client = TestClient(self.app)


class TestConfigEndpoint(ConfigTestCase):

    def test_config_reports_the_env_path_and_gemini_only(self):
        body = self.client.get("/api/config").json()
        self.assertEqual(set(body), {"envPath", "gemini"})
        self.assertEqual(body["envPath"], str(self.env_path))


class TestGeminiEndpoints(ConfigTestCase):
    """Clave y modelos de Gemini.

    Ningun test sale a la red: el cliente del SDK se sustituye por un doble.
    """

    CLAVE = "AIzaSy-CLAVE-FALSA-PARA-TESTS"

    def setUp(self):
        super().setUp()
        # Sobre la guardia de red: probar la clave lista los modelos.
        from unittest import mock

        from tests._gemini_dobles import ClienteConCatalogo

        parche = mock.patch("core.llm.gemini._cliente_real", ClienteConCatalogo)
        parche.start()
        self.addCleanup(parche.stop)

    def test_al_principio_no_hay_clave_configurada(self):
        gemini = self.client.get("/api/config").json()["gemini"]
        self.assertFalse(gemini["configured"])
        self.assertIsNone(gemini["model"])  # automático: se elige de la lista en vivo

    def test_guardar_la_clave_la_escribe_en_el_env(self):
        respuesta = self.client.post(
            "/api/gemini", json={"apiKey": self.CLAVE, "model": "gemini-2.5-flash"}
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("RIR_GEMINI_API_KEY", self.env_path.read_text(encoding="utf-8"))

        gemini = self.client.get("/api/config").json()["gemini"]
        self.assertTrue(gemini["configured"])
        self.assertEqual(gemini["model"], "gemini-2.5-flash")

    def test_la_clave_nunca_vuelve_entera_al_frontend(self):
        self.client.post("/api/gemini", json={"apiKey": self.CLAVE})
        cuerpo = self.client.get("/api/config").text
        self.assertNotIn(self.CLAVE, cuerpo)
        self.assertIn("…", self.client.get("/api/config").json()["gemini"]["keyMasked"])

    def test_guardar_sin_clave_se_rechaza(self):
        self.assertEqual(self.client.post("/api/gemini", json={"apiKey": "  "}).status_code, 400)

    def test_probar_sin_clave_responde_que_no(self):
        cuerpo = self.client.post("/api/gemini/test").json()
        self.assertFalse(cuerpo["ok"])



if __name__ == "__main__":
    unittest.main()
