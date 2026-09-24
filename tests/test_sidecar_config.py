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

from core.ingestion.synthetic import SyntheticFetcher, total_posts
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


class TestSyntheticSource(unittest.TestCase):
    """La fuente de demostración, que sustituye a Reddit."""

    def test_serves_the_first_page_without_a_cursor(self):
        items, cursor = SyntheticFetcher()("cualquiera", limit=25, sort="new")
        self.assertEqual(len(items), 8)
        self.assertEqual(cursor, "1")

    def test_follows_the_cursor_to_the_second_page(self):
        fetcher = SyntheticFetcher()
        _, cursor = fetcher("x", limit=25, sort="new")
        items, next_cursor = fetcher("x", limit=25, sort="new", cursor=cursor)
        self.assertEqual(len(items), 7)
        self.assertIsNone(next_cursor, "dos paginas y se acaba")

    def test_honours_the_limit(self):
        items, _ = SyntheticFetcher()("x", limit=3, sort="new")
        self.assertEqual(len(items), 3)

    def test_an_exhausted_source_returns_nothing(self):
        items, cursor = SyntheticFetcher()("x", limit=25, sort="new", cursor="9")
        self.assertEqual(items, [])
        self.assertIsNone(cursor)

    def test_items_carry_the_fields_the_graph_needs(self):
        items, _ = SyntheticFetcher()("x", limit=1, sort="new")
        for field in ("id", "subreddit", "title", "selftext", "author",
                      "score", "created_utc", "url"):
            self.assertIn(field, items[0])

    def test_the_corpus_spans_several_communities(self):
        """Sin varias comunidades, ningun cluster podria cualificar."""
        items, _ = SyntheticFetcher()("x", limit=25, sort="new")
        self.assertGreaterEqual(len({item["subreddit"] for item in items}), 4)

    def test_total_posts_is_reported(self):
        self.assertEqual(total_posts(), 15)


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

    def eventos(respuesta):
        """El cuerpo NDJSON del plan, evento a evento (AUD-020)."""
        import json

        return [json.loads(linea) for linea in respuesta.text.splitlines() if linea]


if __name__ == "__main__":
    unittest.main()
