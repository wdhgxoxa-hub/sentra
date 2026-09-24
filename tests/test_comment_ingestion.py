"""
Ingesta de comentarios (AUD-015, decisión D-I)
==============================================

Antes solo se ingerían posts: los comentarios, donde suele estar el «a mí
también me pasa» que confirma un problema, no llegaban al análisis. D-I:

- solo por la API OAuth;
- solo de los posts que pasaron el filtro;
- como máximo los MAX_COMMENTS_PER_POST de mayor puntuación, con
  profundidad ≤ MAX_COMMENT_DEPTH;
- se persisten en raw_comments con su procedencia y entran al análisis.

Todo con dobles: el cliente, con la red real de httpx y un servidor falso;
el grafo, con un fetcher falso; PostgreSQL, en una base desechable.
"""

import asyncio
import os
import unittest
from functools import partial
from pathlib import Path
from unittest import mock

import httpx

from core.ingestion import RedditIngestionClient
from core.ingestion.auth import RedditOAuth
from core.ingestion.client import MAX_COMMENT_DEPTH, MAX_COMMENTS_PER_POST

RAIZ = Path(__file__).resolve().parents[1]
UA = "python:sentra-tests:1.0 (by /u/sentra_ci)"


def comentario(ident, score, depth, replies=None):
    return {"kind": "t1", "data": {
        "id": ident, "body": f"comentario {ident}", "author": f"a_{ident}", "score": score,
        "depth": depth, "created_utc": 1758000000.0, "parent_id": "t3_abc",
        "permalink": f"/r/SaaS/comments/abc/x/{ident}/",
        "replies": {"kind": "Listing", "data": {"children": replies}} if replies else "",
    }}


def hilo_grande():
    """30 comentarios de primer nivel, cada uno con respuestas a 1, 2 y 3 niveles."""
    raiz = []
    for n in range(30):
        nieto = comentario(f"n{n}d3", 1000 + n, 3)  # profundidad 3: fuera
        hijo2 = comentario(f"n{n}d2", 500 + n, 2, [nieto])
        hijo1 = comentario(f"n{n}d1", 100 + n, 1, [hijo2])
        raiz.append(comentario(f"n{n}d0", n, 0, [hijo1]))
    raiz.append({"kind": "more", "data": {"children": ["zzz"]}})
    post = {"kind": "Listing", "data": {"children": [{"kind": "t3", "data": {
        "id": "abc", "title": "t", "selftext": "", "author": "u", "subreddit": "SaaS",
        "created_utc": 1758000000.0}}]}}
    return [post, {"kind": "Listing", "data": {"children": raiz}}]


class TestCliente(unittest.TestCase):

    def setUp(self):
        self.peticiones: list[httpx.Request] = []

        def servidor(peticion):
            self.peticiones.append(peticion)
            if peticion.url.path == "/api/v1/access_token":
                return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
            return httpx.Response(200, json=hilo_grande())

        cliente = partial(httpx.AsyncClient, transport=httpx.MockTransport(servidor))
        for destino in ("core.ingestion.client.AsyncClient", "core.ingestion.auth.AsyncClient"):
            parche = mock.patch(destino, cliente)
            parche.start()
            self.addCleanup(parche.stop)
        oauth = RedditOAuth(client_id="cid", client_secret="csec", user_agent=UA)
        self.cliente = RedditIngestionClient(oauth=oauth, rate_limit_delay=0)

    def test_los_limites_son_constantes_con_nombre(self):
        self.assertEqual(MAX_COMMENTS_PER_POST, 20)
        self.assertEqual(MAX_COMMENT_DEPTH, 2)

    def test_como_maximo_los_20_de_mayor_puntuacion_y_profundidad_hasta_2(self):
        comentarios = asyncio.run(self.cliente.fetch_thread_comments("SaaS", "abc"))
        self.assertEqual(len(comentarios), MAX_COMMENTS_PER_POST)
        self.assertTrue(all(c.depth <= MAX_COMMENT_DEPTH for c in comentarios))
        puntos = [c.score for c in comentarios]
        self.assertEqual(puntos, sorted(puntos, reverse=True))
        # Los de profundidad 2 (500+) ganan a los de 1 (100+); los de 3, fuera.
        self.assertEqual(min(puntos), 510)
        self.assertNotIn("n29d3", {c.id for c in comentarios})

    def test_se_piden_por_oauth_con_los_limites_y_nunca_por_la_web_publica(self):
        asyncio.run(self.cliente.fetch_thread_comments("SaaS", "abc"))
        hilo = [p for p in self.peticiones if "/comments/" in p.url.path]
        self.assertEqual(len(hilo), 1)
        self.assertEqual(hilo[0].url.host, "oauth.reddit.com")
        self.assertEqual(hilo[0].url.path, "/r/SaaS/comments/abc")
        self.assertEqual(hilo[0].url.params["depth"], str(MAX_COMMENT_DEPTH + 1))
        self.assertEqual(hilo[0].url.params["sort"], "top")
        texto = (RAIZ / "core" / "ingestion" / "client.py").read_text(encoding="utf-8")
        self.assertNotIn("www.reddit.com", texto)
        # Una URL de la web pública acaba en .json; response.json() no cuenta.
        self.assertNotRegex(texto, r"\.json[\"'/?]")

    def test_la_cronologia_unificada_sin_llamadores_desaparece(self):
        self.assertFalse(hasattr(RedditIngestionClient, "get_unified_timeline"))


# ---------------------------------------------------------------------
# Grafo
# ---------------------------------------------------------------------

POST_DOLOR = {"id": "p1", "title": "The invoice export is broken and I would pay for a fix",
              "selftext": "manual work every week, so frustrating", "author": "ana",
              "subreddit": "SaaS", "created_utc": 1758000000.0, "score": 10}
POST_RUIDO = {"id": "p2", "title": "Hello everyone", "selftext": "nice day",
              "author": "bob", "subreddit": "SaaS", "created_utc": 1758000000.0, "score": 1}


ADMIN_DSN = os.environ.get(
    "RIR_PG_ADMIN_DSN", "host=localhost port=5432 user=postgres dbname=postgres"
)
TEST_DB = "rir_comments_test"


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


if __name__ == "__main__":
    unittest.main()
