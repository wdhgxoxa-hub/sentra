"""
Acceso a Reddit: fallos explícitos y tipados (AUD-003)
======================================================

Sin credenciales, o con Reddit respondiendo 401/403/404/429/5xx, un escaneo
tiene que FALLAR diciendo por qué. Nunca terminar «completado con 0
resultados» ni caer en silencio al endpoint público `.json`.

La red se sustituye por una sesión doble que reproduce los códigos y cuerpos
de Reddit. Ninguna petición sale del proceso.
"""

import asyncio
import json
import logging
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar
from unittest import mock

from fastapi.testclient import TestClient

from core.ingestion import RedditIngestionClient
from core.ingestion.auth import RedditOAuth
from core.ingestion.errors import (
    RedditAccessError,
    RedditAuthFailed,
    RedditCredentialsMissing,
    RedditForbidden,
    RedditNotFound,
    RedditRateLimited,
    RedditUnavailable,
)
from core.orchestration import RadarDependencies
from core.orchestration.pipeline import RedditFetcher
from core.orchestration.sidecar_server import create_app
from core.storage import HashEmbedder, HybridSearchEngine, LanceDBStore

ADMIN_DSN = os.environ.get(
    "RIR_PG_ADMIN_DSN", "host=localhost port=5432 user=postgres dbname=postgres"
)
TEST_DB = "rir_access_errors_test"


def _postgres_available() -> bool:
    try:
        import psycopg

        with psycopg.connect(ADMIN_DSN, connect_timeout=3):
            return True
    except Exception:  # noqa: BLE001 - sondeo de disponibilidad del servidor de pruebas
        return False


POSTGRES_AVAILABLE = _postgres_available()


# ---------------------------------------------------------------------
# Red doble
# ---------------------------------------------------------------------

class RespuestaDoble:
    def __init__(self, status_code, cuerpo=None, headers=None, texto=None):
        self.status_code = status_code
        self._cuerpo = cuerpo
        self.headers = headers or {}
        self._texto = texto

    def json(self):
        if self._texto is not None:
            # Reddit sirve HTML (redireccion a login) con 200 en el acceso anonimo.
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._cuerpo


class SesionDoble:
    """Sustituye a `curl_cffi.requests.AsyncSession`. Anota cada URL pedida."""

    peticiones: ClassVar[list[str]] = []
    respuesta: ClassVar[RespuestaDoble | None] = None
    error: ClassVar[BaseException | None] = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        SesionDoble.peticiones.append(url)
        if SesionDoble.error is not None:
            raise SesionDoble.error
        return SesionDoble.respuesta


def _listado(ids, after=None):
    return {"data": {"after": after, "children": [
        {"kind": "t3", "data": {"id": i, "title": f"t {i}", "selftext": "",
                                "author": "u", "subreddit": "SaaS",
                                "created_utc": 1758000000.0, "permalink": f"/r/SaaS/{i}"}}
        for i in ids
    ]}}


def _oauth():
    async def token(payload, headers):
        return {"access_token": "tok", "expires_in": 3600}

    return RedditOAuth(client_id="cid", client_secret="csec", token_fetcher=token)


class ConRedDoble(unittest.TestCase):

    def setUp(self):
        logging.disable(logging.CRITICAL)
        SesionDoble.peticiones = []
        SesionDoble.respuesta = None
        SesionDoble.error = None
        parche = mock.patch("core.ingestion.client.AsyncSession", SesionDoble)
        parche.start()
        self.addCleanup(parche.stop)
        dormir = mock.patch("core.ingestion.client.asyncio.sleep", mock.AsyncMock())
        dormir.start()
        self.addCleanup(dormir.stop)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def assertNuncaTocaElEndpointPublico(self):
        for url in SesionDoble.peticiones:
            self.assertNotIn("www.reddit.com", url)
            self.assertFalse(url.endswith(".json"), url)


# ---------------------------------------------------------------------
# Cliente de ingesta
# ---------------------------------------------------------------------

class TestClienteDeIngesta(ConRedDoble):

    def _pagina(self, oauth):
        client = RedditIngestionClient(oauth=oauth, rate_limit_delay=0)
        return asyncio.run(client.fetch_subreddit_page("SaaS", limit=5))

    def _falla_con(self, status, tipo, codigo, headers=None):
        SesionDoble.respuesta = RespuestaDoble(status, {"message": "x"}, headers)
        with self.assertRaises(tipo) as ctx:
            self._pagina(_oauth())
        self.assertEqual(ctx.exception.code, codigo)
        self.assertNuncaTocaElEndpointPublico()
        return ctx.exception

    def test_sin_credenciales_falla_sin_ninguna_peticion(self):
        with self.assertRaises(RedditCredentialsMissing) as ctx:
            self._pagina(None)
        self.assertEqual(ctx.exception.code, "reddit_credentials_missing")
        self.assertEqual(SesionDoble.peticiones, [])

    def test_401_es_fallo_de_autenticacion(self):
        self._falla_con(401, RedditAuthFailed, "reddit_auth_failed")

    def test_403_es_acceso_prohibido(self):
        self._falla_con(403, RedditForbidden, "reddit_forbidden")

    def test_404_es_subreddit_inexistente_o_privado(self):
        self._falla_con(404, RedditNotFound, "reddit_not_found")

    def test_429_informa_de_los_segundos_de_retry_after(self):
        error = self._falla_con(429, RedditRateLimited, "reddit_rate_limited",
                                headers={"Retry-After": "30"})
        self.assertEqual(error.retry_after_seconds, 30)

    def test_5xx_es_servicio_no_disponible(self):
        self._falla_con(503, RedditUnavailable, "reddit_unavailable")

    def test_red_caida_es_servicio_no_disponible(self):
        SesionDoble.error = ConnectionResetError("conexion cortada")
        with self.assertRaises(RedditUnavailable):
            self._pagina(_oauth())
        self.assertNuncaTocaElEndpointPublico()

    def test_un_200_que_no_es_json_no_se_toma_por_pagina_vacia(self):
        SesionDoble.respuesta = RespuestaDoble(200, texto="<html>login</html>")
        with self.assertRaises(RedditUnavailable):
            self._pagina(_oauth())

    def test_un_200_con_lista_vacia_es_el_unico_cero_valido(self):
        SesionDoble.respuesta = RespuestaDoble(200, _listado([]))
        self.assertEqual(self._pagina(_oauth()), ([], None))

    def test_todos_los_errores_comparten_una_raiz_tipada(self):
        for tipo in (RedditCredentialsMissing, RedditAuthFailed, RedditForbidden,
                     RedditNotFound, RedditRateLimited, RedditUnavailable):
            self.assertTrue(issubclass(tipo, RedditAccessError), tipo)


class TestTokenOAuth(unittest.TestCase):

    def test_un_401_del_endpoint_de_token_es_fallo_de_autenticacion(self):
        class SesionToken(SesionDoble):
            async def post(self, url, **kwargs):
                return RespuestaDoble(401, {"message": "Unauthorized"})

        auth = RedditOAuth(client_id="cid", client_secret="mal")
        with (
            mock.patch("curl_cffi.requests.AsyncSession", SesionToken),
            self.assertRaises(RedditAuthFailed),
        ):
            asyncio.run(auth.get_token())


# ---------------------------------------------------------------------
# Escaneo completo a través del sidecar
# ---------------------------------------------------------------------

def _eventos(raw):
    eventos = []
    for bloque in raw.strip().split("\n\n"):
        for linea in bloque.splitlines():
            if linea.startswith("data:"):
                eventos.append(json.loads(linea[5:].strip()))
    return eventos


class EscaneoConRedDoble(ConRedDoble):

    def setUp(self):
        super().setUp()
        self.tmpdir = Path(tempfile.mkdtemp(prefix="rir_access_"))
        self.store = LanceDBStore(
            db_path=str(self.tmpdir / "lance"), embedder=HashEmbedder(dim=32)
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        super().tearDown()

    def _app(self, fetcher, **kwargs):
        deps = RadarDependencies(
            fetcher=fetcher, store=self.store,
            search_engine=HybridSearchEngine(store=self.store),
        )
        return TestClient(create_app(deps=deps, env_path=str(self.tmpdir / ".env"),
                                     **kwargs))

    def _fetcher_autenticado(self):
        return RedditFetcher(client=RedditIngestionClient(oauth=_oauth(), rate_limit_delay=0))


class TestEscaneoQueFalla(EscaneoConRedDoble):

    def test_sin_credenciales_el_flujo_termina_en_error_con_codigo(self):
        app = self._app(RedditFetcher(env_path=str(self.tmpdir / ".env")),
                        persist_default=False)
        eventos = _eventos(app.post("/api/scan/stream", json={"subreddit": "SaaS"}).text)
        final = eventos[-1]
        self.assertEqual(final["type"], "run:error")
        self.assertEqual(final["code"], "reddit_credentials_missing")
        self.assertEqual(SesionDoble.peticiones, [])

    def test_un_403_termina_en_error_y_no_en_completado(self):
        SesionDoble.respuesta = RespuestaDoble(403, {"message": "Forbidden"})
        app = self._app(self._fetcher_autenticado(), persist_default=False)
        eventos = _eventos(app.post("/api/scan/stream", json={"subreddit": "SaaS"}).text)
        self.assertEqual(eventos[-1]["type"], "run:error")
        self.assertEqual(eventos[-1]["code"], "reddit_forbidden")
        self.assertNotIn("run:finished", [e["type"] for e in eventos])
        self.assertNuncaTocaElEndpointPublico()

    def test_el_429_viaja_con_los_segundos_de_espera(self):
        SesionDoble.respuesta = RespuestaDoble(429, {}, {"Retry-After": "12"})
        app = self._app(self._fetcher_autenticado(), persist_default=False)
        final = _eventos(app.post("/api/scan/stream", json={"subreddit": "SaaS"}).text)[-1]
        self.assertEqual(final["code"], "reddit_rate_limited")
        self.assertEqual(final["retryAfterSeconds"], 12)

    def test_el_escaneo_sin_flujo_informa_del_fallo(self):
        SesionDoble.respuesta = RespuestaDoble(404, {"message": "Not Found"})
        app = self._app(self._fetcher_autenticado(), persist_default=False)
        cuerpo = app.post("/api/scan", json={"subreddit": "noexiste"}).json()
        self.assertEqual(cuerpo["status"], "failed")
        self.assertEqual(cuerpo["failureCode"], "reddit_not_found")

    def test_un_listado_vacio_real_si_termina_como_completado(self):
        SesionDoble.respuesta = RespuestaDoble(200, _listado([]))
        app = self._app(self._fetcher_autenticado(), persist_default=False)
        final = _eventos(app.post("/api/scan/stream", json={"subreddit": "SaaS"}).text)[-1]
        self.assertEqual(final["type"], "run:finished")


@unittest.skipUnless(POSTGRES_AVAILABLE, "PostgreSQL no disponible")
class TestRunFallidoEnPostgres(EscaneoConRedDoble):

    @classmethod
    def setUpClass(cls):
        import psycopg

        from scripts.migrate import migrate

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        cls.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")
        migrate(cls.dsn, Path(__file__).resolve().parents[1] / "sql" / "migrations")

    @classmethod
    def tearDownClass(cls):
        import psycopg

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')

    def _ultimo_run(self):
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            return conn.execute(
                "SELECT status::text AS status, errors, fetched "
                "FROM radar.pipeline_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()

    def test_el_run_queda_fallido_con_motivo_legible(self):
        SesionDoble.respuesta = RespuestaDoble(403, {"message": "Forbidden"})
        app = self._app(self._fetcher_autenticado(), persist_default=True,
                        postgres_dsn=self.dsn)
        final = _eventos(app.post("/api/scan/stream", json={"subreddit": "SaaS"}).text)[-1]
        self.assertEqual(final["type"], "run:error")
        self.assertIsNotNone(final["persistedRunId"])

        run = self._ultimo_run()
        self.assertEqual(run["status"], "failed")
        self.assertTrue(any("reddit_forbidden" in e for e in run["errors"]), run["errors"])


if __name__ == "__main__":
    unittest.main()
