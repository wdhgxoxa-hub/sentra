"""
Suite de configuración del sidecar
==================================

Cubre lo que la vista de Configuración necesita del backend: consultar y
cambiar la fuente de datos, y guardar y probar las credenciales de Reddit
sin abrir una terminal.

Ningún test escribe en el `.env` real ni sale a la red.
"""

import logging
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar

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
            return True, "Token obtenido (scope: *)", None

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
            return False, "HTTP 401: invalid_grant", "reddit_auth_failed"

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


class TestBlueprintEndpoint(ConfigTestCase):
    """El endpoint que sintetiza la especificacion de proyecto."""

    CLUSTER: ClassVar[dict[str, Any]] = {
        "clusterKey": "complaint:invoice|manual",
        "label": "invoice + manual",
        "intentType": "complaint",
        "keywords": ["invoice", "manual"],
        "subreddits": ["SaaS", "accounting"],
        "mentionCount": 4,
        "communityCount": 2,
        "jobStatement": "algo",
        "currentSolutions": [],
        "paidSignalFactor": 1.0,
        "severityFactor": 0.8,
        "recencyFactor": 0.9,
        "finalScore": 74.0,
        "urgencyTier": "HIGH",
        "evidence": [
            {"quote": "todo roto", "subreddit": "SaaS", "author": "ana", "url": "u"}
        ],
    }

    def _pedir(self, **extra):
        cuerpo = {"cluster": self.CLUSTER}
        cuerpo.update(extra)
        return self.client.post("/api/blueprint", json=cuerpo)

    def test_devuelve_el_documento_completo(self):
        respuesta = self._pedir()
        self.assertEqual(respuesta.status_code, 200)
        cuerpo = respuesta.json()
        for clave in ("productName", "oneLiner", "problem", "mvp", "markdown"):
            self.assertIn(clave, cuerpo)
        # La primera linea declara la fuente (AUD-009); el titulo va despues.
        self.assertTrue(cuerpo["markdown"].startswith("> "))
        self.assertIn(chr(10) + "# ", cuerpo["markdown"])
        self.assertIn("sourceNotice", cuerpo)

    def test_respeta_el_idioma_pedido(self):
        self.assertIn("Resumen", self._pedir(language="es").json()["markdown"])
        self.assertIn("Executive", self._pedir(language="en").json()["markdown"])

    def test_un_cluster_sin_datos_no_tumba_el_sidecar(self):
        respuesta = self.client.post("/api/blueprint", json={"cluster": {}})
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()["markdown"].strip())

    def test_el_puente_recibe_las_citas_deduplicadas(self):
        repetida = {"quote": "igual", "subreddit": "SaaS", "author": "a", "url": "u"}
        cluster = dict(self.CLUSTER, evidence=[repetida, dict(repetida)])
        cuerpo = self.client.post("/api/blueprint", json={"cluster": cluster}).json()
        self.assertEqual(len(cuerpo["evidence"]), 1)
        self.assertEqual(cuerpo["distinctQuotes"], 1)


class TestGeminiEndpoints(ConfigTestCase):
    """Clave de Gemini y generacion de arquitectura.

    Ningun test sale a la red: el cliente del SDK se sustituye por un doble.
    """

    CLAVE = "AIzaSy-CLAVE-FALSA-PARA-TESTS"

    CLUSTER: ClassVar[dict[str, Any]] = {
        "label": "invoice + manual",
        "keywords": ["invoice"],
        "subreddits": ["SaaS"],
        "mentionCount": 3,
        "urgencyTier": "HIGH",
        "breakdown": {"finalScore": 74.0, "paidSignalFactor": 1.0},
        "evidence": [],
    }

    def test_al_principio_no_hay_clave_configurada(self):
        gemini = self.client.get("/api/config").json()["gemini"]
        self.assertFalse(gemini["configured"])
        self.assertEqual(gemini["model"], "gemini-2.5-pro")

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

    def test_generar_sin_clave_responde_412_y_no_llama_al_modelo(self):
        respuesta = self.client.post(
            "/api/architect/generate", json={"cluster": self.CLUSTER}
        )
        self.assertEqual(respuesta.status_code, 412)

    def test_generar_devuelve_el_texto_en_trozos(self):
        from unittest import mock

        self.client.post("/api/gemini", json={"apiKey": self.CLAVE})

        def falso(cluster, **kwargs):
            yield "# FASE 1"
            yield "\ncontenido"

        with mock.patch(
            "core.intelligence.gemini_architect.stream_architecture", falso
        ):
            respuesta = self.client.post(
                "/api/architect/generate",
                json={"cluster": self.CLUSTER, "language": "es"},
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("# FASE 1", respuesta.text)
        self.assertIn("contenido", respuesta.text)

    def test_generar_usa_el_modelo_guardado(self):
        from unittest import mock

        self.client.post(
            "/api/gemini", json={"apiKey": self.CLAVE, "model": "gemini-2.5-flash"}
        )
        vistos = {}

        def falso(cluster, **kwargs):
            vistos.update(kwargs)
            yield "ok"

        with mock.patch(
            "core.intelligence.gemini_architect.stream_architecture", falso
        ):
            self.client.post("/api/architect/generate", json={"cluster": self.CLUSTER})

        self.assertEqual(vistos["model"], "gemini-2.5-flash")
        self.assertEqual(vistos["api_key"], self.CLAVE)

    def test_un_fallo_del_modelo_viaja_como_error_y_no_tumba_el_sidecar(self):
        from unittest import mock

        self.client.post("/api/gemini", json={"apiKey": self.CLAVE})

        def falso(cluster, **kwargs):
            yield "algo"
            raise RuntimeError("se cayo el servicio")

        with mock.patch(
            "core.intelligence.gemini_architect.stream_architecture", falso
        ):
            respuesta = self.client.post(
                "/api/architect/generate", json={"cluster": self.CLUSTER}
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("se cayo el servicio", respuesta.text)
        self.assertEqual(self.client.get("/api/health").status_code, 200)


class TestTranslateEndpoint(ConfigTestCase):
    """Traduccion de citas. Sin clave configurada usa el motor sin conexion."""

    def test_devuelve_una_traduccion_por_texto(self):
        respuesta = self.client.post(
            "/api/translate",
            json={"texts": ["Manual invoice workflow is broken", "Nice to meet you all."],
                  "target": "es"},
        )
        self.assertEqual(respuesta.status_code, 200)
        traducciones = respuesta.json()["translations"]
        self.assertEqual(len(traducciones), 2)
        self.assertEqual(traducciones[0]["engine"], "offline")

    def test_traduce_el_corpus_de_demostracion(self):
        cuerpo = self.client.post(
            "/api/translate",
            json={"texts": ["Manual invoice workflow is broken"], "target": "es"},
        ).json()
        self.assertIn("roto", cuerpo["translations"][0]["text"].lower())
        self.assertFalse(cuerpo["translations"][0]["approximate"])

    def test_lo_desconocido_vuelve_marcado_como_aproximado(self):
        cuerpo = self.client.post(
            "/api/translate",
            json={"texts": ["Quuxbar zyzzyva frobnicate"], "target": "es"},
        ).json()
        self.assertTrue(cuerpo["translations"][0]["approximate"])

    def test_sin_textos_responde_una_lista_vacia(self):
        cuerpo = self.client.post("/api/translate", json={"texts": []}).json()
        self.assertEqual(cuerpo["translations"], [])

    def test_rechaza_tandas_desproporcionadas(self):
        respuesta = self.client.post(
            "/api/translate", json={"texts": ["x"] * 200, "target": "es"}
        )
        self.assertEqual(respuesta.status_code, 422)

    def test_un_idioma_desconocido_no_revienta(self):
        respuesta = self.client.post(
            "/api/translate", json={"texts": ["hello"], "target": "klingon"}
        )
        self.assertEqual(respuesta.status_code, 200)
