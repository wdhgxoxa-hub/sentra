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
import unittest
from functools import partial
from typing import ClassVar
from unittest import mock

import httpx

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

ADMIN_DSN = os.environ.get(
    "RIR_PG_ADMIN_DSN", "host=localhost port=5432 user=postgres dbname=postgres"
)
TEST_DB = "rir_access_errors_test"


def _postgres_available() -> bool:
    try:
        import psycopg
    except ImportError:
        return False
    try:
        with psycopg.connect(ADMIN_DSN, connect_timeout=3):
            return True
    except psycopg.Error:
        return False


POSTGRES_AVAILABLE = _postgres_available()


# ---------------------------------------------------------------------
# Red doble
# ---------------------------------------------------------------------

#: User-Agent con el formato que exige Reddit (AUD-014).
UA = "python:sentra-tests:1.0 (by /u/sentra_ci)"


class RespuestaDoble:
    """Lo que Reddit contestaría: se convierte en una respuesta real de httpx."""

    def __init__(self, status_code, cuerpo=None, headers=None, texto=None):
        self.status_code = status_code
        self._cuerpo = cuerpo
        self.headers = headers or {}
        self._texto = texto

    def a_httpx(self) -> httpx.Response:
        if self._texto is not None:
            # Reddit sirve HTML (redireccion a login) con 200 en el acceso anonimo.
            return httpx.Response(self.status_code, text=self._texto, headers=self.headers)
        return httpx.Response(self.status_code, json=self._cuerpo, headers=self.headers)


class SesionDoble:
    """Red falsa bajo httpx (`MockTransport`): anota cada URL y responde lo fijado.

    El cliente usa su AsyncClient real; solo el transporte es de mentira.
    """

    peticiones: ClassVar[list[str]] = []
    respuesta: ClassVar[RespuestaDoble | None] = None
    error: ClassVar[BaseException | None] = None

    @classmethod
    def manejar(cls, peticion: httpx.Request) -> httpx.Response:
        cls.peticiones.append(f"{peticion.url.scheme}://{peticion.url.host}{peticion.url.path}")
        if cls.error is not None:
            raise cls.error
        assert cls.respuesta is not None, "el test no fijó respuesta"
        return cls.respuesta.a_httpx()


def cliente_http_falso(manejador):
    """AsyncClient de httpx con el transporte sustituido."""
    return partial(httpx.AsyncClient, transport=httpx.MockTransport(manejador))


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

    return RedditOAuth(client_id="cid", client_secret="csec", user_agent=UA,
                       token_fetcher=token)


class ConRedDoble(unittest.TestCase):

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        SesionDoble.peticiones = []
        SesionDoble.respuesta = None
        SesionDoble.error = None
        parche = mock.patch("core.ingestion.client.AsyncClient",
                            cliente_http_falso(SesionDoble.manejar))
        parche.start()
        self.addCleanup(parche.stop)
        dormir = mock.patch("core.ingestion.client.asyncio.sleep", mock.AsyncMock())
        dormir.start()
        self.addCleanup(dormir.stop)

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
        SesionDoble.error = httpx.ConnectError("conexion cortada")
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
        def token(_peticion):
            return RespuestaDoble(401, {"message": "Unauthorized"}).a_httpx()

        auth = RedditOAuth(client_id="cid", client_secret="mal", user_agent=UA)
        with (
            mock.patch("core.ingestion.auth.AsyncClient", cliente_http_falso(token)),
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


if __name__ == "__main__":
    unittest.main()
