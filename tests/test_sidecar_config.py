"""
Suite de configuración del sidecar
==================================

Cubre lo que la vista de Configuración necesita del backend: consultar y
cambiar la fuente de datos, y guardar y probar las credenciales de Reddit
sin abrir una terminal.

Ningún test escribe en el `.env` real ni sale a la red.
"""

import logging
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from core.ingestion.synthetic import SyntheticFetcher, total_posts
from core.orchestration import RadarDependencies
from core.orchestration.sidecar_server import create_app
from core.storage import HashEmbedder, HybridSearchEngine, LanceDBStore

TEST_DIM = 64


def setUpModule():
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


class ConfigTestCase(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="rir_config_"))
        self.env_path = self.tmpdir / ".env"
        self.store = LanceDBStore(
            db_path=str(self.tmpdir / "lance"), embedder=HashEmbedder(dim=TEST_DIM)
        )
        self.deps = RadarDependencies(
            fetcher=SyntheticFetcher(),
            store=self.store,
            search_engine=HybridSearchEngine(store=self.store),
        )
        self.app = create_app(
            deps=self.deps, persist_default=False, env_path=str(self.env_path)
        )
        self.client = TestClient(self.app)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)


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

    def test_config_reports_the_active_source(self):
        body = self.client.get("/api/config").json()
        self.assertEqual(body["fetcherMode"], "synthetic")

    def test_config_reports_whether_credentials_exist(self):
        body = self.client.get("/api/config").json()
        self.assertFalse(body["credentials"]["configured"])

    def test_config_never_returns_the_secret(self):
        """Un secreto que viaja al frontend acaba en el log de alguien."""
        self.client.post("/api/credentials", json={
            "clientId": "mi-id", "clientSecret": "mi-secreto-largo",
            "userAgent": "radar/1.0",
        })
        raw = self.client.get("/api/config").text
        self.assertNotIn("mi-secreto-largo", raw)

    def test_config_shows_a_masked_client_id(self):
        self.client.post("/api/credentials", json={
            "clientId": "abcdef123456", "clientSecret": "s", "userAgent": "ua",
        })
        body = self.client.get("/api/config").json()
        self.assertTrue(body["credentials"]["configured"])
        self.assertIn("…", body["credentials"]["clientIdMasked"])
        self.assertNotIn("abcdef123456", body["credentials"]["clientIdMasked"])


class TestSourceSwitch(ConfigTestCase):

    def test_switching_to_reddit_changes_the_source(self):
        body = self.client.post("/api/config/mode", json={"mode": "reddit"}).json()
        self.assertEqual(body["fetcherMode"], "reddit")

    def test_the_change_takes_effect_without_restarting(self):
        self.client.post("/api/config/mode", json={"mode": "reddit"})
        self.assertEqual(self.deps.fetcher.__class__.__name__, "RedditFetcher")

    def test_switching_back_to_synthetic_works(self):
        self.client.post("/api/config/mode", json={"mode": "reddit"})
        self.client.post("/api/config/mode", json={"mode": "synthetic"})
        self.assertIsInstance(self.deps.fetcher, SyntheticFetcher)

    def test_an_unknown_mode_is_rejected(self):
        response = self.client.post("/api/config/mode", json={"mode": "inventado"})
        self.assertEqual(response.status_code, 422)


class TestCredentials(ConfigTestCase):

    def test_saving_creates_the_env_file(self):
        response = self.client.post("/api/credentials", json={
            "clientId": "cid", "clientSecret": "csec", "userAgent": "radar/1.0",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.env_path.exists())

    def test_the_env_file_contains_the_keys(self):
        self.client.post("/api/credentials", json={
            "clientId": "cid", "clientSecret": "csec", "userAgent": "radar/1.0",
        })
        content = self.env_path.read_text(encoding="utf-8")
        self.assertIn("RIR_REDDIT_CLIENT_ID=cid", content)
        self.assertIn("RIR_REDDIT_CLIENT_SECRET=csec", content)

    def test_saving_twice_updates_instead_of_duplicating(self):
        for secret in ("primero", "segundo"):
            self.client.post("/api/credentials", json={
                "clientId": "cid", "clientSecret": secret, "userAgent": "ua",
            })
        content = self.env_path.read_text(encoding="utf-8")
        self.assertEqual(content.count("RIR_REDDIT_CLIENT_SECRET="), 1)
        self.assertIn("segundo", content)

    def test_unrelated_lines_in_the_env_are_preserved(self):
        """El .env tiene mas cosas que las credenciales de Reddit."""
        self.env_path.write_text(
            "# comentario\nRIR_PG_DSN=host=localhost\nOTRA=cosa\n", encoding="utf-8"
        )
        self.client.post("/api/credentials", json={
            "clientId": "cid", "clientSecret": "csec", "userAgent": "ua",
        })
        content = self.env_path.read_text(encoding="utf-8")
        self.assertIn("RIR_PG_DSN=host=localhost", content)
        self.assertIn("OTRA=cosa", content)
        self.assertIn("# comentario", content)

    def test_an_empty_client_id_is_rejected(self):
        response = self.client.post("/api/credentials", json={
            "clientId": "   ", "clientSecret": "csec", "userAgent": "ua",
        })
        self.assertEqual(response.status_code, 422)

    def test_optional_user_credentials_are_stored_when_given(self):
        self.client.post("/api/credentials", json={
            "clientId": "cid", "clientSecret": "csec", "userAgent": "ua",
            "username": "usuario", "password": "clave",
        })
        content = self.env_path.read_text(encoding="utf-8")
        self.assertIn("RIR_REDDIT_USERNAME=usuario", content)


class TestCredentialsProbe(ConfigTestCase):
    """Probar la conexión sin salir a la red: el obtentor se inyecta."""

    def test_probing_without_credentials_reports_it(self):
        body = self.client.post("/api/credentials/test").json()
        self.assertFalse(body["ok"])
        self.assertIn("credenciales", body["detail"].lower())

    def test_a_successful_probe_is_reported(self):
        import core.orchestration.sidecar_server as sidecar

        async def fake_probe(auth):
            return True, "Token obtenido (scope: *)"

        original = sidecar._probe_reddit
        sidecar._probe_reddit = fake_probe
        try:
            self.client.post("/api/credentials", json={
                "clientId": "cid", "clientSecret": "csec", "userAgent": "ua",
            })
            body = self.client.post("/api/credentials/test").json()
        finally:
            sidecar._probe_reddit = original

        self.assertTrue(body["ok"])
        self.assertIn("Token", body["detail"])

    def test_a_failed_probe_explains_why(self):
        import core.orchestration.sidecar_server as sidecar

        async def fake_probe(auth):
            return False, "HTTP 401: invalid_grant"

        original = sidecar._probe_reddit
        sidecar._probe_reddit = fake_probe
        try:
            self.client.post("/api/credentials", json={
                "clientId": "cid", "clientSecret": "csec", "userAgent": "ua",
            })
            body = self.client.post("/api/credentials/test").json()
        finally:
            sidecar._probe_reddit = original

        self.assertFalse(body["ok"])
        self.assertIn("401", body["detail"])


if __name__ == "__main__":
    unittest.main()
