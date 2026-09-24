"""
Suite del servidor sidecar (deuda D14)
======================================

El sidecar expone por HTTP local lo que Rust no resuelve por su cuenta: las
fuentes y su escaneo, el juez, la búsqueda sobre la evidencia, la
configuración de Gemini y la salud. La pipeline antigua de Reddit (escaneo
por subreddit, credenciales de Reddit, documentos por cluster, traducción)
se retiró (C2): sus rutas no pueden volver sin cambiar la superficie de
aquí abajo.

Las pruebas usan el cliente de FastAPI, que habla con la aplicación en
memoria: no se abre ningún puerto ni se toca la red.
"""

import logging
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from core.orchestration.sidecar_server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    create_app,
)
from tests._sin_red import prohibir_red_real

#: Tokens con la forma de los de la aplicación: 64 hex (D-B).
TOKEN_PRUEBA = "5e" * 32
OTRO_TOKEN = "a1" * 32


def setUpModule():
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


class SidecarTestCase(unittest.TestCase):
    """Base con una aplicación sin persistencia y con un `.env` temporal."""

    token: str | None = None

    def setUp(self):
        prohibir_red_real(self)
        self.tmpdir = tempfile.mkdtemp(prefix="rir_sidecar_")
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        self.app = create_app(token=self.token, persist_default=False,
                              env_path=str(Path(self.tmpdir) / ".env"),
                              insecure_dev=self.token is None)
        self.client = TestClient(self.app)


class TestDefaults(unittest.TestCase):

    def test_binds_to_loopback_only(self):
        """El sidecar no debe escuchar en toda la red del equipo."""
        self.assertEqual(DEFAULT_HOST, "127.0.0.1")

    def test_default_port_is_documented(self):
        self.assertEqual(DEFAULT_PORT, 8765)


class TestHealth(SidecarTestCase):

    def test_health_responds_ok_with_uptime_and_persistence(self):
        cuerpo = self.client.get("/api/health").json()
        self.assertEqual(cuerpo["status"], "ok")
        self.assertGreaterEqual(cuerpo["uptimeSeconds"], 0)
        self.assertEqual(cuerpo["persistence"], {"enabled": False, "target": None})

    def test_health_no_longer_describes_the_old_pipeline(self):
        # C2: el embedder, el NLI y el almacén LanceDB de señales eran de la
        # pipeline antigua, igual que el estado del escáner de Reddit.
        cuerpo = self.client.get("/api/health").json()
        for antiguo in ("embedder", "nli", "store", "source"):
            self.assertNotIn(antiguo, cuerpo)


class TestCancellation(SidecarTestCase):
    """La cancelación del escaneo multifuente (sus flujos, en test_sidecar_multiscan)."""

    def test_cancelling_an_unknown_run_reports_it_was_not_active(self):
        body = self.client.post("/api/scan/cancel", json={"runId": "no-existe"}).json()
        self.assertFalse(body["wasActive"])

    def test_cancel_is_protected_by_the_token(self):
        app = create_app(token=TOKEN_PRUEBA, persist_default=False)
        response = TestClient(app).post("/api/scan/cancel", json={"runId": "x"})
        self.assertEqual(response.status_code, 401)


class TestAuthentication(SidecarTestCase):
    """
    Un servidor HTTP en localhost es alcanzable por cualquier proceso del
    equipo, y el escaneo consume cuota de las fuentes. El token se exige en
    `Authorization: Bearer` (D-B); tests/test_sidecar_token.py recorre todos
    los endpoints.
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
        response = self.client.post("/api/sources/scan/stream", json={"topic": "x"})
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
                "/api/scan/cancel",
                "/api/search",
                "/api/config",
                "/api/gemini",
                "/api/gemini/test",
                "/api/gemini/models",
                "/api/sources",
                "/api/sources/{source_id}/credentials",
                "/api/sources/{source_id}/probe",
                "/api/sources/{source_id}/enabled",
                "/api/sources/commercial-mode",
                "/api/sources/scan/stream",
                "/api/judge/top",
                "/api/evidence/recent",
            },
        )


if __name__ == "__main__":
    unittest.main()
