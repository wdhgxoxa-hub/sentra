"""
Acceso a Reddit: fallos explícitos y tipados (AUD-003)
======================================================

Lo que queda del acceso antiguo a Reddit tras retirar el cliente de ingesta
(D-C7) es la autenticación OAuth, que reutiliza el adaptador de Reddit: un
401 del endpoint de token tiene que llegar como fallo de autenticación
tipado, nunca como una respuesta vacía.

La red se sustituye por un transporte doble de httpx. Ninguna petición sale
del proceso.
"""

import asyncio
import unittest
from functools import partial
from unittest import mock

import httpx

from core.ingestion.auth import RedditOAuth
from core.ingestion.errors import RedditAuthFailed

#: User-Agent con el formato que exige Reddit (AUD-014).
UA = "python:sentra-tests:1.0 (by /u/sentra_ci)"


def cliente_http_falso(manejador):
    """AsyncClient de httpx con el transporte sustituido."""
    return partial(httpx.AsyncClient, transport=httpx.MockTransport(manejador))


class TestTokenOAuth(unittest.TestCase):

    def test_un_401_del_endpoint_de_token_es_fallo_de_autenticacion(self):
        def token(_peticion):
            return httpx.Response(401, json={"message": "Unauthorized"})

        auth = RedditOAuth(client_id="cid", client_secret="mal", user_agent=UA)
        with (
            mock.patch("core.ingestion.auth.AsyncClient", cliente_http_falso(token)),
            self.assertRaises(RedditAuthFailed),
        ):
            asyncio.run(auth.get_token())


if __name__ == "__main__":
    unittest.main()
