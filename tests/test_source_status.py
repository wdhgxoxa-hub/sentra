"""
Estado real de la fuente de datos (AUD-004)
===========================================

El indicador tiene que decir si SENTRA puede leer Reddit de verdad, no qué
modo se eligió. `reddit_verificado` solo se alcanza tras una respuesta 200
real de la API OAuth: un escaneo en modo Reddit que no falló, o una prueba
de conexión que obtuvo token.

La red es un doble: ningún test sale de la máquina.
"""

import logging
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from core.ingestion.errors import RedditForbidden
from core.ingestion.synthetic import SyntheticFetcher
from core.orchestration import RadarDependencies
from core.orchestration.pipeline import RedditFetcher
from core.orchestration.sidecar import config as sidecar_config
from core.orchestration.sidecar_server import create_app
from core.storage import HashEmbedder, HybridSearchEngine, LanceDBStore


class ClienteDoble:
    """Cliente de ingesta sin red. `fallo` simula la respuesta de Reddit."""

    fallo: Exception | None = None

    def __init__(self, oauth):
        self.oauth = oauth

    async def fetch_subreddit_page(self, **_kwargs):
        if ClienteDoble.fallo is not None:
            raise ClienteDoble.fallo
        return [], None


class TestEstadoDeLaFuente(unittest.TestCase):

    def setUp(self):
        logging.disable(logging.CRITICAL)
        ClienteDoble.fallo = None
        self.tmpdir = Path(tempfile.mkdtemp(prefix="rir_fuente_"))
        self.env_path = str(self.tmpdir / ".env")
        store = LanceDBStore(db_path=str(self.tmpdir / "lance"), embedder=HashEmbedder(dim=32))
        self.deps = RadarDependencies(
            fetcher=SyntheticFetcher(), store=store,
            search_engine=HybridSearchEngine(store=store),
        )
        self.client = TestClient(
            create_app(insecure_dev=True, deps=self.deps, persist_default=False, env_path=self.env_path)
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        logging.disable(logging.NOTSET)

    # -- ayudas ----------------------------------------------------------

    def _fuente(self):
        return self.client.get("/api/health").json()["source"]

    def _modo_reddit(self):
        self.assertEqual(
            self.client.post("/api/config/mode", json={"mode": "reddit"}).status_code, 200
        )
        # El sidecar crea un RedditFetcher propio; se le da un cliente sin red.
        self.deps.fetcher = RedditFetcher(env_path=self.env_path, client_factory=ClienteDoble)

    def _guardar_credenciales(self, client_id="cid"):
        r = self.client.post("/api/credentials", json={
            "clientId": client_id, "clientSecret": "csec", "userAgent": "python:sentra-tests:1.0 (by /u/sentra_ci)"})
        self.assertEqual(r.status_code, 200, r.text)

    def _escanear(self):
        self.client.post("/api/scan", json={"subreddit": "SaaS", "limit": 5})

    # -- transiciones ----------------------------------------------------

    def test_con_datos_fabricados_el_estado_es_demo(self):
        self.assertEqual(self._fuente()["state"], "demo")

    def test_en_modo_reddit_sin_credenciales(self):
        self._modo_reddit()
        self.assertEqual(self._fuente()["state"], "reddit_sin_credenciales")

    def test_credenciales_guardadas_pero_sin_probar(self):
        self._modo_reddit()
        self._guardar_credenciales()
        fuente = self._fuente()
        self.assertEqual(fuente["state"], "reddit_sin_verificar")
        self.assertIsNone(fuente["lastSuccessAt"])

    def test_un_escaneo_con_200_real_verifica_y_fecha_el_acceso(self):
        self._modo_reddit()
        self._guardar_credenciales()
        self._escanear()
        fuente = self._fuente()
        self.assertEqual(fuente["state"], "reddit_verificado")
        self.assertIsNotNone(fuente["lastSuccessAt"])

    def test_un_escaneo_rechazado_es_error_con_su_codigo(self):
        self._modo_reddit()
        self._guardar_credenciales()
        ClienteDoble.fallo = RedditForbidden("403")
        self._escanear()
        fuente = self._fuente()
        self.assertEqual(fuente["state"], "reddit_error")
        self.assertEqual(fuente["errorCode"], "reddit_forbidden")

    def test_un_error_posterior_quita_el_verde(self):
        self._modo_reddit()
        self._guardar_credenciales()
        self._escanear()
        ClienteDoble.fallo = RedditForbidden("403")
        self._escanear()
        self.assertEqual(self._fuente()["state"], "reddit_error")

    def test_credenciales_nuevas_vuelven_a_sin_verificar(self):
        self._modo_reddit()
        self._guardar_credenciales("cid-A")
        self._escanear()
        self._guardar_credenciales("cid-B")
        fuente = self._fuente()
        self.assertEqual(fuente["state"], "reddit_sin_verificar")
        self.assertIsNone(fuente["lastSuccessAt"])

    def test_la_prueba_de_conexion_correcta_verifica(self):
        self._modo_reddit()
        self._guardar_credenciales()

        async def sonda(auth):
            return True, "ok", None

        with mock.patch.object(sidecar_config, "_probe_reddit", sonda):
            self.client.post("/api/credentials/test")
        self.assertEqual(self._fuente()["state"], "reddit_verificado")

    def test_la_prueba_de_conexion_fallida_es_error(self):
        self._modo_reddit()
        self._guardar_credenciales()

        async def sonda(auth):
            return False, "rechazadas", "reddit_auth_failed"

        with mock.patch.object(sidecar_config, "_probe_reddit", sonda):
            self.client.post("/api/credentials/test")
        fuente = self._fuente()
        self.assertEqual(fuente["state"], "reddit_error")
        self.assertEqual(fuente["errorCode"], "reddit_auth_failed")

    def test_un_escaneo_de_demostracion_nunca_verifica_reddit(self):
        # Credenciales guardadas, pero el escaneo lo sirve el corpus fabricado.
        self._guardar_credenciales()
        self._escanear()
        self._modo_reddit()
        self.assertEqual(self._fuente()["state"], "reddit_sin_verificar")


if __name__ == "__main__":
    unittest.main()
