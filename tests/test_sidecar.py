"""
Suite del servidor sidecar (deuda D14)
======================================

El sidecar expone por HTTP local lo único que Rust no puede resolver por su
cuenta: ejecutar el grafo y buscar sobre LanceDB.

Las pruebas usan el cliente de FastAPI, que habla con la aplicación en
memoria: no se abre ningún puerto ni se toca la red.
"""

import logging
import shutil
import tempfile
import unittest

from fastapi.testclient import TestClient

from core.orchestration import RadarDependencies
from core.orchestration.sidecar_server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    create_app,
)
from core.storage import HashEmbedder, HybridSearchEngine, LanceDBStore
from tests._sin_red import prohibir_red_real

TEST_DIM = 64

#: Tokens con la forma de los de la aplicación: 64 hex (D-B).
TOKEN_PRUEBA = "5e" * 32
OTRO_TOKEN = "a1" * 32

PAIN_POST = {
    "id": "t3_pain",
    "subreddit": "smallbusiness",
    "title": "Manual invoice export is broken",
    "selftext": (
        "The export is completely broken and it is frustrating. "
        "I would pay for a tool that fixes this manual invoice process."
    ),
    "author": "u/frustrated",
    "score": 120,
    "created_utc": 4102444800.0,
    "url": "https://reddit.com/r/smallbusiness/pain",
}


def setUpModule():
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


class SidecarTestCase(unittest.TestCase):
    """Base con una aplicación montada sobre dependencias falsas."""

    token: str | None = None

    def setUp(self):
        prohibir_red_real(self)
        self.tmpdir = tempfile.mkdtemp(prefix="rir_sidecar_")
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        self.store = LanceDBStore(
            db_path=self.tmpdir, embedder=HashEmbedder(dim=TEST_DIM)
        )
        self.calls = []

        def fetcher(subreddit, limit, sort, cursor=None):
            self.calls.append({"subreddit": subreddit, "limit": limit, "sort": sort})
            return ([PAIN_POST], None) if cursor is None else ([], None)

        self.deps = RadarDependencies(
            fetcher=fetcher,
            store=self.store,
            search_engine=HybridSearchEngine(store=self.store),
        )
        self.app = create_app(deps=self.deps, token=self.token, persist_default=False,
                              insecure_dev=self.token is None)
        self.client = TestClient(self.app)



class TestDefaults(unittest.TestCase):

    def test_binds_to_loopback_only(self):
        """El sidecar no debe escuchar en toda la red del equipo."""
        self.assertEqual(DEFAULT_HOST, "127.0.0.1")

    def test_default_port_is_documented(self):
        self.assertEqual(DEFAULT_PORT, 8765)


class TestHealth(SidecarTestCase):

    def test_health_responds(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)

    def test_health_reports_status_ok(self):
        self.assertEqual(self.client.get("/api/health").json()["status"], "ok")

    def test_health_describes_the_embedder(self):
        embedder = self.client.get("/api/health").json()["embedder"]
        self.assertEqual(embedder["name"], "hash-md5")
        self.assertFalse(embedder["semantic"])
        self.assertEqual(embedder["dim"], TEST_DIM)

    def test_health_reports_the_classifier_engine(self):
        """Sin transformers la clasificación es heurística, y debe constar."""
        nli = self.client.get("/api/health").json()["nli"]
        self.assertIn("engine", nli)
        self.assertIn(nli["engine"], ("heuristic", "transformers"))

    def test_health_reports_the_store(self):
        store = self.client.get("/api/health").json()["store"]
        self.assertIn("records", store)

    def test_health_includes_uptime(self):
        self.assertGreaterEqual(
            self.client.get("/api/health").json()["uptimeSeconds"], 0
        )


class TestScan(SidecarTestCase):

    def test_scan_runs_the_pipeline(self):
        response = self.client.post("/api/scan", json={"subreddit": "smallbusiness"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calls[0]["subreddit"], "smallbusiness")

    def test_scan_forwards_limit_and_sort(self):
        self.client.post(
            "/api/scan", json={"subreddit": "devops", "limit": 7, "sort": "new"}
        )
        self.assertEqual(self.calls[0]["limit"], 7)
        self.assertEqual(self.calls[0]["sort"], "new")

    def test_scan_returns_both_tiers(self):
        body = self.client.post(
            "/api/scan", json={"subreddit": "smallbusiness"}
        ).json()
        self.assertIn("qualified", body)
        self.assertIn("qualifiedClusters", body)
        self.assertIn("clusters", body)

    def test_scan_returns_statistics(self):
        body = self.client.post(
            "/api/scan", json={"subreddit": "smallbusiness"}
        ).json()
        self.assertIn("fetched", body["stats"])
        self.assertEqual(body["stats"]["fetched"], 1)

    def test_scan_reports_the_run_id_when_not_persisting(self):
        body = self.client.post(
            "/api/scan", json={"subreddit": "smallbusiness", "persist": False}
        ).json()
        self.assertIsNone(body["runId"])

    def test_scan_requires_a_subreddit(self):
        self.assertEqual(self.client.post("/api/scan", json={}).status_code, 422)

    def test_scan_rejects_an_empty_subreddit(self):
        response = self.client.post("/api/scan", json={"subreddit": "   "})
        self.assertEqual(response.status_code, 422)

    def test_persistence_receives_the_full_state_not_the_summary(self):
        """
        Regresion: el sidecar pasaba a persistir el RESUMEN, que descarta
        `signals` y `filtered_items`. La escritura "funcionaba" pero dejaba
        una ejecucion vacia en PostgreSQL.
        """
        import core.orchestration.sidecar.scan as sidecar

        recibido = {}

        async def espia(state, deps, dsn, status="completed", data_source=None, author_salt=None):
            recibido.update(state)
            return "run-falso", True, None

        original = sidecar._persist
        sidecar._persist = espia
        try:
            app = create_app(deps=self.deps, persist_default=True, insecure_dev=True)
            body = TestClient(app).post(
                "/api/scan", json={"subreddit": "smallbusiness"}
            ).json()
        finally:
            sidecar._persist = original

        self.assertTrue(recibido.get("signals"), "faltan las senales analizadas")
        self.assertTrue(recibido.get("filtered_items"), "faltan los posts crudos")
        self.assertEqual(body["runId"], "run-falso")
        self.assertTrue(body["persisted"])
        self.assertIsNone(body["persistError"])

    def test_a_persistence_failure_reports_its_reason(self):
        """
        Un `persisted: false` sin motivo es imposible de diagnosticar: hay
        que saber si fallo la conexion, el esquema o los datos.
        """
        import core.orchestration.sidecar.scan as sidecar

        async def rota(state, deps, dsn, status="completed", data_source=None, author_salt=None):
            return None, False, "OperationalError: no hay conexion"

        original = sidecar._persist
        sidecar._persist = rota
        try:
            app = create_app(deps=self.deps, persist_default=True, insecure_dev=True)
            body = TestClient(app).post(
                "/api/scan", json={"subreddit": "smallbusiness"}
            ).json()
        finally:
            sidecar._persist = original

        self.assertFalse(body["persisted"])
        self.assertIn("no hay conexion", body["persistError"])
        # La cosecha sigue viajando: el escaneo no se pierde.
        self.assertTrue(body["clusters"])

    def test_a_failing_fetcher_is_reported_not_crashed(self):
        def broken(*args, **kwargs):
            raise ConnectionError("reddit no responde")

        app = create_app(
            deps=RadarDependencies(fetcher=broken, store=self.store),
            insecure_dev=True,
            persist_default=False,
        )
        body = TestClient(app).post(
            "/api/scan", json={"subreddit": "x"}
        ).json()
        self.assertTrue(any("reddit no responde" in e for e in body["errors"]))


def _parse_sse(raw: str):
    """Extrae los eventos JSON de un flujo `text/event-stream`."""
    import json

    eventos = []
    separador = "\n\n"
    for bloque in raw.strip().split(separador):
        for linea in bloque.splitlines():
            if linea.startswith("data:"):
                eventos.append(json.loads(linea[5:].strip()))
    return eventos


class TestScanStream(SidecarTestCase):
    """Progreso en tiempo real, para no tener que sondear."""

    def _stream(self, payload=None):
        with self.client.stream(
            "POST", "/api/scan/stream", json=payload or {"subreddit": "smallbusiness"}
        ) as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/event-stream", response.headers["content-type"])
            return _parse_sse("".join(response.iter_text()))

    def test_stream_opens_with_run_started(self):
        eventos = self._stream()
        self.assertEqual(eventos[0]["type"], "run:started")
        self.assertEqual(eventos[0]["subreddit"], "smallbusiness")
        self.assertTrue(eventos[0]["runId"])

    def test_stream_emits_progress_for_every_node(self):
        eventos = self._stream()
        nodos = [e["node"] for e in eventos if e["type"] == "run:progress"]
        self.assertEqual(
            nodos,
            ["fetch", "filter", "comments", "intelligence", "storage", "quality_gate",
             "aggregate"],
        )

    def test_progress_carries_the_accumulated_statistics(self):
        eventos = self._stream()
        avance = [e for e in eventos if e["type"] == "run:progress"]
        self.assertEqual(avance[0]["stats"]["fetched"], 1)
        self.assertIn("clusters", avance[-1]["stats"])

    def test_progress_carries_the_cycle_number(self):
        eventos = self._stream()
        avance = [e for e in eventos if e["type"] == "run:progress"]
        self.assertTrue(all(e["cycle"] >= 1 for e in avance))

    def test_stream_closes_with_run_finished(self):
        eventos = self._stream()
        self.assertEqual(eventos[-1]["type"], "run:finished")
        self.assertIn("qualified", eventos[-1])
        self.assertIn("clusters", eventos[-1])

    def test_the_same_run_id_travels_in_every_event(self):
        """Sin un identificador estable no se pueden correlacionar los eventos."""
        eventos = self._stream()
        ids = {e["runId"] for e in eventos}
        self.assertEqual(len(ids), 1)

    def test_a_failing_pipeline_emits_run_error(self):
        def broken(*args, **kwargs):
            raise RuntimeError("el grafo exploto")

        deps = RadarDependencies(fetcher=broken, store=self.store)
        app = create_app(deps=deps, persist_default=False, insecure_dev=True)
        # Una fuente que no entrega datos es un fallo de la ejecucion, no una
        # cosecha vacia (AUD-003): nada de "run:finished".
        with TestClient(app).stream(
            "POST", "/api/scan/stream", json={"subreddit": "x"}
        ) as response:
            eventos = _parse_sse("".join(response.iter_text()))
        tipos = {e["type"] for e in eventos}
        self.assertIn("run:started", tipos)
        self.assertNotIn("run:finished", tipos)
        self.assertEqual(eventos[-1]["type"], "run:error")
        self.assertEqual(eventos[-1]["code"], "fetch_failed")

    def test_stream_is_protected_by_the_token_too(self):
        app = create_app(deps=self.deps, token=TOKEN_PRUEBA, persist_default=False)
        response = TestClient(app).post(
            "/api/scan/stream", json={"subreddit": "x"}
        )
        self.assertEqual(response.status_code, 401)


class TestCancellation(SidecarTestCase):
    """
    Cancelacion cooperativa: el grafo se interrumpe ENTRE nodos, no a mitad
    de uno. Matar un nodo a media escritura dejaria el almacen inconsistente,
    y un escaneo cancelado debe poder conservar lo ya cosechado.
    """

    def test_cancelling_an_unknown_run_reports_it_was_not_active(self):
        body = self.client.post(
            "/api/scan/cancel", json={"runId": "no-existe"}
        ).json()
        self.assertFalse(body["wasActive"])

    def test_a_scan_can_be_cancelled_before_it_starts(self):
        """
        Se pre-registra la cancelacion y luego se lanza el escaneo con ese
        mismo id: el flujo debe cortarse en la primera comprobacion.
        """
        run_id = "run-de-prueba"
        self.client.post("/api/scan/cancel", json={"runId": run_id})

        with self.client.stream(
            "POST", "/api/scan/stream",
            json={"subreddit": "smallbusiness", "runId": run_id},
        ) as response:
            eventos = _parse_sse("".join(response.iter_text()))

        tipos = [e["type"] for e in eventos]
        self.assertIn("run:cancelled", tipos)
        self.assertNotIn("run:finished", tipos)

    def test_a_cancelled_scan_does_not_run_every_node(self):
        run_id = "run-cortado"
        self.client.post("/api/scan/cancel", json={"runId": run_id})

        with self.client.stream(
            "POST", "/api/scan/stream",
            json={"subreddit": "smallbusiness", "runId": run_id},
        ) as response:
            eventos = _parse_sse("".join(response.iter_text()))

        nodos = [e["node"] for e in eventos if e["type"] == "run:progress"]
        self.assertLess(len(nodos), 6, "no deberia completar el grafo entero")

    def test_the_client_can_propose_the_run_id(self):
        """Sin poder fijar el id, no hay forma de cancelar lo que aun no existe."""
        with self.client.stream(
            "POST", "/api/scan/stream",
            json={"subreddit": "smallbusiness", "runId": "id-elegido"},
        ) as response:
            eventos = _parse_sse("".join(response.iter_text()))
        self.assertEqual(eventos[0]["runId"], "id-elegido")

    def test_cancellation_is_forgotten_after_the_run_ends(self):
        """Si no se olvidara, el siguiente escaneo con ese id naceria muerto."""
        run_id = "run-reutilizado"
        self.client.post("/api/scan/cancel", json={"runId": run_id})
        with self.client.stream(
            "POST", "/api/scan/stream",
            json={"subreddit": "smallbusiness", "runId": run_id},
        ) as response:
            response.read()

        with self.client.stream(
            "POST", "/api/scan/stream",
            json={"subreddit": "smallbusiness", "runId": run_id},
        ) as response:
            eventos = _parse_sse("".join(response.iter_text()))
        self.assertEqual(eventos[-1]["type"], "run:finished")

    def test_cancel_is_protected_by_the_token(self):
        app = create_app(deps=self.deps, token=TOKEN_PRUEBA, persist_default=False)
        response = TestClient(app).post("/api/scan/cancel", json={"runId": "x"})
        self.assertEqual(response.status_code, 401)


class TestSearch(SidecarTestCase):

    def _index(self):
        self.client.post("/api/scan", json={"subreddit": "smallbusiness"})

    def test_search_finds_an_indexed_signal(self):
        self._index()
        body = self.client.post(
            "/api/search", json={"query": "invoice export"}
        ).json()
        self.assertIn("t3_pain", {hit["id"] for hit in body["hits"]})

    def test_search_exposes_the_rrf_breakdown(self):
        self._index()
        hit = self.client.post(
            "/api/search", json={"query": "invoice export"}
        ).json()["hits"][0]
        for field in ("rrfScore", "denseRank", "bm25Rank"):
            self.assertIn(field, hit)

    def test_search_honours_the_minimum_score(self):
        self._index()
        body = self.client.post(
            "/api/search", json={"query": "invoice export", "minScore": 99.9}
        ).json()
        self.assertEqual(body["hits"], [])

    def test_search_honours_the_limit(self):
        self._index()
        body = self.client.post(
            "/api/search", json={"query": "invoice", "limit": 1}
        ).json()
        self.assertLessEqual(len(body["hits"]), 1)

    def test_empty_query_is_rejected(self):
        response = self.client.post("/api/search", json={"query": "   "})
        self.assertEqual(response.status_code, 422)

    def test_search_without_index_returns_nothing(self):
        body = self.client.post("/api/search", json={"query": "cualquiera"}).json()
        self.assertEqual(body["hits"], [])


class TestAuthentication(SidecarTestCase):
    """
    Un servidor HTTP en localhost es alcanzable por cualquier proceso del
    equipo, y `scan` consume cuota de la API de Reddit. El token se exige
    en `Authorization: Bearer` (D-B); tests/test_sidecar_token.py recorre
    todos los endpoints.
    """

    token = TOKEN_PRUEBA

    def test_request_without_token_is_rejected(self):
        self.assertEqual(self.client.get("/api/health").status_code, 401)

    def test_request_with_the_wrong_token_is_rejected(self):
        response = self.client.get(
            "/api/health", headers={"Authorization": f"Bearer {OTRO_TOKEN}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_request_with_the_right_token_passes(self):
        response = self.client.get(
            "/api/health", headers={"Authorization": f"Bearer {self.token}"}
        )
        self.assertEqual(response.status_code, 200)

    def test_scan_is_protected_too(self):
        response = self.client.post("/api/scan", json={"subreddit": "x"})
        self.assertEqual(response.status_code, 401)


class TestWithoutToken(SidecarTestCase):
    """Con --insecure-dev explícito, el sidecar sirve sin token (desarrollo)."""

    token = None

    def test_health_is_reachable(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)


class TestSurface(SidecarTestCase):

    def test_only_the_documented_routes_exist(self):
        paths = {
            route.path
            for route in self.app.routes
            if getattr(route, "path", "").startswith("/api")
        }
        self.assertEqual(
            paths,
            {
                "/api/health",
                "/api/scan",
                "/api/scan/stream",
                "/api/scan/cancel",
                "/api/search",
                "/api/config",
                "/api/config/mode",
                "/api/credentials",
                "/api/credentials/test",
                "/api/blueprint",
                "/api/gemini",
                "/api/gemini/test",
                "/api/gemini/models",
                "/api/architect/generate",
                "/api/translate",
                "/api/document/pdf",
            },
        )


if __name__ == "__main__":
    unittest.main()
