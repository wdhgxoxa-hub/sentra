"""
Credenciales de Reddit sin reiniciar (AUD-012)
==============================================

Lo que se guarda desde Configuración tiene que ser lo que use el siguiente
escaneo, y lo mismo que pruebe «Probar conexión». Ningún test toca el `.env`
real ni sale a la red: el cliente de Reddit es un doble que anota con qué
credenciales se construyó.
"""

import logging
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from core.orchestration import RadarDependencies, sidecar_server
from core.orchestration.pipeline import RedditFetcher
from core.orchestration.sidecar_server import create_app
from core.storage import HashEmbedder, HybridSearchEngine, LanceDBStore

CLAVES_REDDIT = (
    "RIR_REDDIT_CLIENT_ID",
    "RIR_REDDIT_CLIENT_SECRET",
    "RIR_REDDIT_USERNAME",
    "RIR_REDDIT_PASSWORD",
    "RIR_REDDIT_USER_AGENT",
)


class ClienteDoble:
    """Cliente de ingesta que no sale a la red: devuelve un listado vacío."""

    def __init__(self, oauth):
        self.oauth = oauth

    async def fetch_subreddit_page(self, **_kwargs):
        return [], None


class TestCredencialesSinReiniciar(unittest.TestCase):

    def setUp(self):
        logging.disable(logging.CRITICAL)
        # El entorno del proceso no puede aportar credenciales a la prueba.
        self._entorno = {k: os.environ.pop(k) for k in CLAVES_REDDIT if k in os.environ}

        self.tmpdir = Path(tempfile.mkdtemp(prefix="rir_cred_"))
        self.env_path = str(self.tmpdir / ".env")
        self.construidos = []

        def fabrica(oauth):
            self.construidos.append(oauth)
            return ClienteDoble(oauth)

        store = LanceDBStore(
            db_path=str(self.tmpdir / "lance"), embedder=HashEmbedder(dim=32)
        )
        deps = RadarDependencies(
            fetcher=RedditFetcher(env_path=self.env_path, client_factory=fabrica),
            store=store,
            search_engine=HybridSearchEngine(store=store),
        )
        self.client = TestClient(
            create_app(insecure_dev=True, deps=deps, persist_default=False, env_path=self.env_path)
        )

    def tearDown(self):
        for clave in CLAVES_REDDIT:
            os.environ.pop(clave, None)
        os.environ.update(self._entorno)
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        logging.disable(logging.NOTSET)

    def _guardar(self, client_id):
        respuesta = self.client.post(
            "/api/credentials",
            json={"clientId": client_id, "clientSecret": f"secreto-{client_id}",
                  "userAgent": "python:sentra-tests:1.0 (by /u/sentra_ci)"},
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.text)

    def _escanear(self):
        respuesta = self.client.post("/api/scan", json={"subreddit": "SaaS", "limit": 5})
        self.assertEqual(respuesta.status_code, 200, respuesta.text)
        self.assertTrue(self.construidos, "el escaneo no construyo ningun cliente")
        return self.construidos[-1]

    def test_el_escaneo_usa_las_credenciales_recien_guardadas(self):
        self._guardar("cliente-A")
        self.assertEqual(self._escanear().client_id, "cliente-A")

        self._guardar("cliente-B")
        self.assertEqual(
            self._escanear().client_id, "cliente-B",
            "las credenciales nuevas no llegan al escaneo sin reiniciar",
        )

    def test_la_prueba_y_el_escaneo_ven_las_mismas_credenciales(self):
        self._guardar("cliente-A")
        self._escanear()
        self._guardar("cliente-B")

        probadas = []

        async def sonda(auth):
            probadas.append(auth.client_id)
            return True, "ok", None

        with mock.patch.object(sidecar_server, "_probe_reddit", sonda):
            self.client.post("/api/credentials/test")

        self.assertEqual(probadas, ["cliente-B"])
        self.assertEqual(self._escanear().client_id, probadas[0])

    def test_leer_credenciales_no_contamina_el_entorno_del_proceso(self):
        self._guardar("cliente-A")
        self._escanear()
        # assertFalse y no assertNotIn: el mensaje de fallo de assertNotIn
        # vuelca el entorno entero, secretos incluidos.
        self.assertFalse(
            "RIR_REDDIT_CLIENT_ID" in os.environ,
            "la lectura de credenciales escribio en os.environ",
        )


if __name__ == "__main__":
    unittest.main()
