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
import shutil
import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest import mock

import httpx

from core.ingestion import RedditIngestionClient
from core.ingestion.auth import RedditOAuth
from core.ingestion.client import MAX_COMMENT_DEPTH, MAX_COMMENTS_PER_POST
from core.orchestration import RadarDependencies, RadarPipeline
from core.storage import HashEmbedder, HybridSearchEngine, LanceDBStore

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


class FetcherConComentarios:
    """Fetcher falso: dos posts (uno con dolor, otro ruido) y sus comentarios."""

    def __init__(self):
        self.pedidos: list[tuple[str, str]] = []

    def __call__(self, subreddit, limit=25, sort="hot", cursor=None):
        return [POST_DOLOR, POST_RUIDO], None

    def fetch_comments(self, subreddit, post_id):
        self.pedidos.append((subreddit, post_id))
        return [
            {"id": "t1_c1", "kind": "comment", "post_id": post_id, "depth": 0, "score": 7,
             "body": "Same here, the invoice export breaks every month and it is so frustrating",
             "author": "carla", "subreddit": subreddit, "created_utc": 1758000100.0,
             "permalink": "https://reddit.com/r/SaaS/comments/p1/x/c1/"},
            {"id": "t1_c2", "kind": "comment", "post_id": post_id, "depth": 1, "score": 1,
             "body": "lol", "author": "dan", "subreddit": subreddit,
             "created_utc": 1758000200.0, "permalink": ""},
        ]


class ConGrafo(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rir_comentarios_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.store = LanceDBStore(db_path=str(self.tmp / "lance"), embedder=HashEmbedder(dim=32))
        self.fetcher = FetcherConComentarios()
        self.estado = RadarPipeline(deps=RadarDependencies(
            fetcher=self.fetcher, store=self.store,
            search_engine=HybridSearchEngine(store=self.store),
        )).run_state("SaaS")



class TestGrafo(ConGrafo):

    def test_solo_se_piden_comentarios_de_los_posts_que_pasaron_el_filtro(self):
        self.assertEqual(self.fetcher.pedidos, [("SaaS", "p1")])

    def test_los_comentarios_se_guardan_todos_y_se_analizan_los_que_pasan_el_filtro(self):
        self.assertEqual({c["id"] for c in self.estado["all_comments"]}, {"t1_c1", "t1_c2"})
        analizadas = {s.id for s in self.estado["all_signals"]}
        self.assertIn("t1_c1", analizadas)
        self.assertNotIn("t1_c2", analizadas)

    def test_un_comentario_no_se_confunde_con_un_post(self):
        self.assertNotIn("t1_c1", {i["id"] for i in self.estado["all_items"]})

    def test_el_comentario_analizado_llega_a_lancedb_con_su_fuente(self):
        fila = self.store.get_by_id("t1_c1")
        self.assertIsNotNone(fila)
        self.assertEqual(fila["data_source"], "demo")


ADMIN_DSN = os.environ.get(
    "RIR_PG_ADMIN_DSN", "host=localhost port=5432 user=postgres dbname=postgres"
)
TEST_DB = "rir_comments_test"


def _postgres_available() -> bool:
    try:
        import psycopg

        with psycopg.connect(ADMIN_DSN, connect_timeout=3):
            return True
    except Exception:  # noqa: BLE001 - sondeo de disponibilidad del servidor de pruebas
        return False


@unittest.skipUnless(_postgres_available(), "PostgreSQL no disponible")
class TestPersistencia(ConGrafo):

    def test_los_comentarios_se_persisten_con_su_post_su_fuente_y_su_senal(self):
        import psycopg

        from core.storage.postgres_store import PostgresStore, run_async
        from scripts.migrate import migrate

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")
        try:
            migrate(dsn, RAIZ / "sql" / "migrations")

            async def escribir():
                async with PostgresStore(dsn=dsn) as pg:
                    return await pg.persist_state(self.estado, data_source="reddit")

            resultado = run_async(escribir())
            self.assertEqual(resultado["comments"], 2)
            with psycopg.connect(dsn) as conn:
                conn.execute("SET search_path = radar, public")
                comentarios = conn.execute(
                    "SELECT c.reddit_id, p.reddit_id, c.data_source, c.depth "
                    "FROM raw_comments c JOIN raw_posts p ON p.id = c.post_id ORDER BY 1"
                ).fetchall()
                senal = conn.execute(
                    "SELECT source_kind::text, comment_id IS NOT NULL, data_source "
                    "FROM analyzed_signals WHERE reddit_id = 't1_c1'"
                ).fetchone()
            self.assertEqual(comentarios, [("t1_c1", "p1", "reddit", 0),
                                           ("t1_c2", "p1", "reddit", 1)])
            self.assertEqual(senal, ("comment", True, "reddit"))
        finally:
            with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
                conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')


if __name__ == "__main__":
    unittest.main()
