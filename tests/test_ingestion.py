"""
Suite de Pruebas Unitarias y de Integración para core/ingestion
==============================================================
Verifica el 100% de los componentes de la Fase 2:
- Filtro léxico y anti-spam (reddit-painpointer & pain-miner)
- Paginación directa por cursor (Bellingcat RPST)
- Normalización, deduplicación e interfoliado cronológico (reddit-find & snscrape)
- Cliente asíncrono de la API OAuth (httpx)
"""

import asyncio
import unittest
from datetime import UTC, datetime
from unittest import mock

from core.ingestion.auth import RedditAuthError, RedditOAuth, load_dotenv
from core.ingestion.client import RedditIngestionClient
from core.ingestion.errors import RedditCredentialsMissing
from core.ingestion.filters import PAIN_POINT_KEYWORDS, PainPointFilter
from core.ingestion.normalizer import (
    CleanComment,
    CleanPost,
    RedditNormalizer,
)
from core.ingestion.pagination import RedditPaginator
from tests._ayudas import presente

#: User-Agent con el formato que exige Reddit (AUD-014).
UA = "python:sentra-tests:1.0 (by /u/sentra_ci)"


class TestPainPointFilter(unittest.TestCase):
    def setUp(self):
        self.filter = PainPointFilter()

    def test_keywords_count(self):
        self.assertEqual(len(PAIN_POINT_KEYWORDS), 33)

    def test_detects_pain_keywords(self):
        sample = (
            "I am spending hours every day managing client work. "
            "It is a tedious process that kills my productivity. "
            "I wish there was a tool to automate this."
        )
        matched = self.filter.match_keywords(sample)
        self.assertIn("spending hours every", matched)
        self.assertIn("tedious process", matched)
        self.assertIn("kills my productivity", matched)
        self.assertIn("wish there was a tool", matched)
        self.assertIn("automate", matched)
        self.assertTrue(self.filter.contains_pain_signal(sample))

    def test_detects_spam_and_affiliates(self):
        spam_text = "Check out our product here with promo code DISCOUNT20 or use ref=partner_123"
        self.assertTrue(self.filter.is_spam_or_affiliate(spam_text))

        clean_text = "Does anyone know how to handle customer invoices efficiently?"
        self.assertFalse(self.filter.is_spam_or_affiliate(clean_text))

    def test_detects_bot_authors(self):
        self.assertTrue(self.filter.is_bot_content("AutoModerator", "Welcome to r/Python!"))
        self.assertTrue(self.filter.is_bot_content("helpful_user_bot", "Here is your link"))
        self.assertTrue(
            self.filter.is_bot_content("user123", "I am a bot, and this action was performed automatically.")
        )
        self.assertFalse(self.filter.is_bot_content("john_developer", "I have an issue with Docker."))

    def test_evaluate_candidate(self):
        # Caso que pasa
        res_pass = self.filter.evaluate(
            text="I hate manually doing this repetitive task every week. Anyone else struggling with this?",
            author="dev_lead",
            require_pain_match=True
        )
        self.assertTrue(res_pass.passed)
        self.assertTrue(res_pass.is_pain_signal)
        self.assertGreater(len(res_pass.matched_keywords), 0)

        # Caso que se rechaza por no tener señal de dolor
        res_no_pain = self.filter.evaluate(
            text="Today the weather is really nice outside.",
            author="normal_user",
            require_pain_match=True
        )
        self.assertFalse(res_no_pain.passed)
        self.assertIn("no_pain_keywords_found", res_no_pain.rejection_reasons)

        # Caso que se rechaza por bot
        res_bot = self.filter.evaluate(
            text="I hate manually doing this tedious process",
            author="AutoModerator",
            require_pain_match=True
        )
        self.assertFalse(res_bot.passed)
        self.assertIn("bot_or_automod_content", res_bot.rejection_reasons)


class TestRedditNormalizer(unittest.TestCase):
    def test_normalize_id(self):
        self.assertEqual(RedditNormalizer.normalize_id("t3_1abc23"), "1abc23")
        self.assertEqual(RedditNormalizer.normalize_id("t1_9xyz45"), "9xyz45")
        self.assertEqual(RedditNormalizer.normalize_id("plain_id"), "plain_id")

    def test_is_deleted_or_removed(self):
        self.assertTrue(RedditNormalizer.is_deleted_or_removed("[deleted]"))
        self.assertTrue(RedditNormalizer.is_deleted_or_removed("[removed]"))
        self.assertTrue(RedditNormalizer.is_deleted_or_removed(""))
        self.assertTrue(RedditNormalizer.is_deleted_or_removed(None))
        self.assertFalse(RedditNormalizer.is_deleted_or_removed("Useful content"))

    def test_deduplication(self):
        posts = [
            CleanPost(id="t3_101", title="Post 1", score=100),
            CleanPost(id="101", title="Duplicate of Post 1", score=90),
            CleanPost(id="t3_102", title="Post 2", score=80),
        ]
        deduped = RedditNormalizer.deduplicate_posts(posts)
        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[0].id, "t3_101")
        self.assertEqual(deduped[1].id, "t3_102")

    def test_chronological_interleaving_snscrape(self):
        posts = [
            CleanPost(id="p1", title="Post 1", created_utc=1000.0),
            CleanPost(id="p2", title="Post 2", created_utc=3000.0),
        ]
        comments = [
            CleanComment(id="c1", body="Comment 1", created_utc=2000.0),
            CleanComment(id="c2", body="Comment 2", created_utc=3000.0),  # Mismo timestamp que p2
        ]

        interleaved = list(RedditNormalizer.interleave_chronological(posts, comments))
        self.assertEqual(len(interleaved), 4)

        # En t=3000, el comentario c2 debe preceder al post p2
        self.assertEqual(interleaved[0].kind, "comment")
        self.assertEqual(interleaved[0].id, "c2")
        self.assertEqual(interleaved[1].kind, "post")
        self.assertEqual(interleaved[1].id, "p2")
        # En t=2000 viene c1
        self.assertEqual(interleaved[2].kind, "comment")
        self.assertEqual(interleaved[2].id, "c1")
        # En t=1000 viene p1
        self.assertEqual(interleaved[3].kind, "post")
        self.assertEqual(interleaved[3].id, "p1")

    def test_markdown_formatters(self):
        posts = [
            CleanPost(
                id="p1",
                subreddit="saas",
                title="Struggling with billing automation",
                selftext="We are wasting hours on invoices every week.",
                author="founder1",
                score=45,
                num_comments=12,
                created_utc=1726650000.0,
                is_pain_signal=True,
                matched_keywords=["automate", "invoice"],
                comments=[
                    CleanComment(id="c1", author="advisor", body="Try Stripe billing webhooks", score=10)
                ]
            )
        ]

        titles_md = RedditNormalizer.format_titles_table("Billing SaaS", ["saas"], posts)
        self.assertIn("| 45 | 12 |", titles_md)
        self.assertIn("🔥 Sí", titles_md)

        deep_md = RedditNormalizer.format_deep_dive_markdown("Billing SaaS", ["saas"], posts)
        self.assertIn("Struggling with billing automation", deep_md)
        self.assertIn("Try Stripe billing webhooks", deep_md)
        self.assertIn("Señales: automate, invoice", deep_md)


class TestRedditPaginator(unittest.TestCase):
    def setUp(self):
        self.paginator = RedditPaginator()

    def test_page_params(self):
        params = self.paginator.build_page_params(listing="top", limit=50, after="t3_next", timeframe="week")
        self.assertEqual(params["limit"], 50)
        self.assertEqual(params["after"], "t3_next")
        self.assertEqual(params["t"], "week")

    def test_recency_filter(self):
        now = datetime.now(UTC).timestamp()
        items = [
            {"id": "recent", "created_utc": now - 3600},       # 1 hora de antigüedad
            {"id": "old", "created_utc": now - (10 * 86400)},  # 10 días de antigüedad
        ]
        filtered, reached = self.paginator.filter_by_recency(items, max_age_days=5)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["id"], "recent")
        self.assertTrue(reached)

    def test_extract_children(self):
        mock_response = {
            "data": {
                "after": "t3_cursor_xyz",
                "children": [
                    {"kind": "t3", "data": {"id": "p1", "title": "Hello"}},
                    {"kind": "t3", "data": {"id": "p2", "title": "World"}}
                ]
            }
        }
        children, after = self.paginator.extract_children_and_after(mock_response)
        self.assertEqual(len(children), 2)
        self.assertEqual(after, "t3_cursor_xyz")
        self.assertEqual(children[0]["title"], "Hello")


class TestRedditIngestionClient(unittest.TestCase):
    def test_client_initialization(self):
        client = RedditIngestionClient(
            timeout_seconds=10.0,
            rate_limit_delay=0.5
        )
        self.assertIsNotNone(client.filter)
        self.assertIsNotNone(client.paginator)
        self.assertIsNotNone(client.normalizer)
        self.assertEqual(client.timeout_seconds, 10.0)


def _reddit_listing(post_ids, after=None):
    """Construye un payload de listado con la forma real que devuelve Reddit."""
    return {
        "kind": "Listing",
        "data": {
            "after": after,
            "dist": len(post_ids),
            "children": [
                {
                    "kind": "t3",
                    "data": {
                        "id": pid,
                        "subreddit": "smallbusiness",
                        "title": f"Manual invoice work is killing me ({pid})",
                        "selftext": "I spend hours every week on this tedious process.",
                        "author": f"u/user_{pid}",
                        "score": 42,
                        "upvote_ratio": 0.97,
                        "num_comments": 7,
                        "created_utc": 1758000000.0,
                        "url": f"https://reddit.com/r/smallbusiness/{pid}",
                        "permalink": f"/r/smallbusiness/comments/{pid}/",
                        "link_flair_text": None,
                    },
                }
                for pid in post_ids
            ],
        },
    }


class TestSubredditPagination(unittest.TestCase):
    """
    Paginación explícita por cursor.

    Se sustituye `_execute_request`, que es la única frontera de red del
    cliente, por una respuesta sintética con la forma real de Reddit. Así se
    ejercita el recorrido completo (parseo, normalización, cursor) sin salir
    a internet.
    """

    def setUp(self):
        # Solo existe la via autenticada (AUD-003): el token lo da un doble.
        async def token(payload, headers):
            return {"access_token": "tok", "expires_in": 3600}

        self.client = RedditIngestionClient(
            oauth=RedditOAuth(client_id="cid", client_secret="csec", user_agent=UA,
                              token_fetcher=token)
        )
        self.requests = []

    def _install_transport(self, pages):
        """Encola respuestas y registra los parámetros de cada petición."""
        queue = list(pages)

        async def fake_execute(url, params=None, **kwargs):
            self.requests.append({"url": url, "params": dict(params or {})})
            return queue.pop(0) if queue else None

        parche = mock.patch.object(self.client, "_execute_request", fake_execute)
        parche.start()
        self.addCleanup(parche.stop)

    def test_page_returns_posts_and_the_next_cursor(self):
        self._install_transport([_reddit_listing(["aaa", "bbb"], after="t3_bbb")])
        posts, cursor = asyncio.run(
            self.client.fetch_subreddit_page("smallbusiness", limit=2)
        )
        self.assertEqual([p.id for p in posts], ["aaa", "bbb"])
        self.assertEqual(cursor, "t3_bbb")

    def test_last_page_reports_no_cursor(self):
        self._install_transport([_reddit_listing(["zzz"], after=None)])
        _, cursor = asyncio.run(
            self.client.fetch_subreddit_page("smallbusiness", limit=1)
        )
        self.assertIsNone(cursor)

    def test_incoming_cursor_is_sent_to_reddit(self):
        self._install_transport([_reddit_listing(["ccc"], after=None)])
        asyncio.run(
            self.client.fetch_subreddit_page(
                "smallbusiness", limit=1, after="t3_previous"
            )
        )
        self.assertEqual(self.requests[0]["params"].get("after"), "t3_previous")

    def test_first_page_sends_no_cursor(self):
        self._install_transport([_reddit_listing(["ddd"], after=None)])
        asyncio.run(self.client.fetch_subreddit_page("smallbusiness", limit=1))
        self.assertNotIn("after", self.requests[0]["params"])

    def test_empty_response_yields_nothing_and_no_cursor(self):
        # El unico "vacio" valido: Reddit responde 200 con una lista vacia.
        self._install_transport([_reddit_listing([], after=None)])
        posts, cursor = asyncio.run(
            self.client.fetch_subreddit_page("smallbusiness", limit=5)
        )
        self.assertEqual(posts, [])
        self.assertIsNone(cursor)

    def test_posts_are_normalized_into_clean_posts(self):
        self._install_transport([_reddit_listing(["eee"], after=None)])
        posts, _ = asyncio.run(
            self.client.fetch_subreddit_page("smallbusiness", limit=1)
        )
        post = posts[0]
        self.assertIsInstance(post, CleanPost)
        self.assertEqual(post.subreddit, "smallbusiness")
        self.assertEqual(post.score, 42)
        self.assertTrue(post.permalink.startswith("https://reddit.com/"))

    def test_fetch_subreddit_posts_still_returns_only_a_list(self):
        """La firma histórica no cambia: sigue devolviendo posts, no tuplas."""
        self._install_transport([_reddit_listing(["fff"], after=None)])
        result = asyncio.run(
            self.client.fetch_subreddit_posts("smallbusiness", limit_per_page=1)
        )
        self.assertIsInstance(result, list)
        self.assertIsInstance(result[0], CleanPost)

    def test_fetch_subreddit_posts_accepts_a_starting_cursor(self):
        self._install_transport([_reddit_listing(["ggg"], after=None)])
        asyncio.run(
            self.client.fetch_subreddit_posts(
                "smallbusiness", limit_per_page=1, after="t3_start"
            )
        )
        self.assertEqual(self.requests[0]["params"].get("after"), "t3_start")

    def test_multi_page_walk_follows_the_cursor_chain(self):
        self._install_transport([
            _reddit_listing(["p1"], after="t3_p1"),
            _reddit_listing(["p2"], after="t3_p2"),
        ])
        posts = asyncio.run(
            self.client.fetch_subreddit_posts(
                "smallbusiness", limit_per_page=1, max_pages=2
            )
        )
        self.assertEqual([p.id for p in posts], ["p1", "p2"])
        self.assertEqual(self.requests[1]["params"].get("after"), "t3_p1")


class TestRedditOAuth(unittest.TestCase):
    """
    Autenticación OAuth2 contra Reddit.

    Reddit cerró el acceso anónimo a los endpoints `.json`, así que la vía
    soportada es una aplicación de tipo *script*. Ningún test pide un token
    real: se inyecta el obtentor de token.
    """

    def setUp(self):
        self.token_requests = []

    def _fetcher(self, token="tok_abc", expires_in=3600):
        async def fetch(payload, headers):
            self.token_requests.append({"payload": dict(payload),
                                        "headers": dict(headers)})
            return {"access_token": token, "token_type": "bearer",
                    "expires_in": expires_in, "scope": "*"}
        return fetch

    def test_is_not_configured_without_credentials(self):
        self.assertFalse(RedditOAuth(client_id=None, client_secret=None).is_configured)

    def test_is_configured_with_id_and_secret(self):
        auth = RedditOAuth(client_id="cid", client_secret="csec")
        self.assertTrue(auth.is_configured)

    def test_from_env_returns_none_without_credentials(self):
        self.assertIsNone(RedditOAuth.from_env(env={}))

    def test_from_env_reads_the_documented_variables(self):
        auth = RedditOAuth.from_env(env={
            "RIR_REDDIT_CLIENT_ID": "cid",
            "RIR_REDDIT_CLIENT_SECRET": "csec",
            "RIR_REDDIT_USER_AGENT": UA,
        })
        self.assertIsNotNone(auth)
        self.assertEqual(presente(auth).client_id, "cid")
        self.assertEqual(presente(auth).user_agent, UA)

    def test_app_only_grant_when_there_is_no_user(self):
        auth = RedditOAuth(client_id="cid", client_secret="csec", user_agent=UA,
                           token_fetcher=self._fetcher())
        asyncio.run(auth.get_token())
        self.assertEqual(
            self.token_requests[0]["payload"]["grant_type"], "client_credentials"
        )

    def test_password_grant_when_a_user_is_supplied(self):
        auth = RedditOAuth(client_id="cid", client_secret="csec", user_agent=UA,
                           username="u", password="p",
                           token_fetcher=self._fetcher())
        asyncio.run(auth.get_token())
        payload = self.token_requests[0]["payload"]
        self.assertEqual(payload["grant_type"], "password")
        self.assertEqual(payload["username"], "u")

    def test_request_carries_basic_auth_and_user_agent(self):
        auth = RedditOAuth(client_id="cid", client_secret="csec", user_agent=UA,
                           token_fetcher=self._fetcher())
        asyncio.run(auth.get_token())
        headers = self.token_requests[0]["headers"]
        self.assertTrue(headers["Authorization"].startswith("Basic "))
        self.assertEqual(headers["User-Agent"], UA)

    def test_token_is_returned(self):
        auth = RedditOAuth(client_id="cid", client_secret="csec", user_agent=UA,
                           token_fetcher=self._fetcher(token="tok_xyz"))
        self.assertEqual(asyncio.run(auth.get_token()), "tok_xyz")

    def test_token_is_cached_between_calls(self):
        auth = RedditOAuth(client_id="cid", client_secret="csec", user_agent=UA,
                           token_fetcher=self._fetcher())

        async def twice():
            await auth.get_token()
            await auth.get_token()

        asyncio.run(twice())
        self.assertEqual(len(self.token_requests), 1, "no deberia repedir el token")

    def test_expired_token_is_renewed(self):
        auth = RedditOAuth(client_id="cid", client_secret="csec", user_agent=UA,
                           token_fetcher=self._fetcher(expires_in=0))

        async def twice():
            await auth.get_token()
            await auth.get_token()

        asyncio.run(twice())
        self.assertEqual(len(self.token_requests), 2)

    def test_unconfigured_client_refuses_to_ask_for_a_token(self):
        with self.assertRaises(RedditAuthError):
            asyncio.run(RedditOAuth().get_token())

    def test_a_response_without_token_is_an_error(self):
        async def broken(payload, headers):
            return {"error": "invalid_grant"}

        auth = RedditOAuth(client_id="cid", client_secret="csec", user_agent=UA,
                           token_fetcher=broken)
        with self.assertRaises(RedditAuthError):
            asyncio.run(auth.get_token())

    def test_credentials_never_appear_in_the_repr(self):
        auth = RedditOAuth(client_id="cid", client_secret="supersecreto",
                           password="clave")
        self.assertNotIn("supersecreto", repr(auth))
        self.assertNotIn("clave", repr(auth))


class TestDotEnvLoading(unittest.TestCase):
    """Carga de credenciales desde un archivo .env, sin dependencias externas."""

    def setUp(self):
        import shutil
        import tempfile

        self.tmpdir = tempfile.mkdtemp(prefix="rir_env_")
        self.addCleanup(shutil.rmtree, self.tmpdir, True)

    def _write(self, content):
        import os
        path = os.path.join(self.tmpdir, ".env")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def test_parses_key_value_pairs(self):
        env: dict[str, str] = {}
        load_dotenv(self._write("RIR_REDDIT_CLIENT_ID=abc\n"), env=env)
        self.assertEqual(env["RIR_REDDIT_CLIENT_ID"], "abc")

    def test_ignores_comments_and_blank_lines(self):
        env: dict[str, str] = {}
        load_dotenv(self._write("# comentario\n\nA=1\n  \n"), env=env)
        self.assertEqual(env, {"A": "1"})

    def test_strips_surrounding_quotes(self):
        env: dict[str, str] = {}
        load_dotenv(self._write('A="con espacios"\nB=\'simple\'\n'), env=env)
        self.assertEqual(env["A"], "con espacios")
        self.assertEqual(env["B"], "simple")

    def test_does_not_override_an_existing_variable(self):
        env = {"A": "del_entorno"}
        load_dotenv(self._write("A=del_fichero\n"), env=env)
        self.assertEqual(env["A"], "del_entorno")

    def test_a_missing_file_is_not_an_error(self):
        env: dict[str, str] = {}
        load_dotenv(self.tmpdir + "/no_existe", env=env)
        self.assertEqual(env, {})

    def test_value_containing_equals_is_preserved(self):
        env: dict[str, str] = {}
        load_dotenv(self._write("A=x=y=z\n"), env=env)
        self.assertEqual(env["A"], "x=y=z")


class TestAuthenticatedFetch(unittest.TestCase):
    """El cliente debe hablar con oauth.reddit.com cuando hay credenciales."""

    def setUp(self):
        self.requests = []

    def _client(self, with_auth):
        auth = None
        if with_auth:
            async def fetch(payload, headers):
                return {"access_token": "tok_abc", "expires_in": 3600}
            auth = RedditOAuth(client_id="cid", client_secret="csec", user_agent=UA,
                               token_fetcher=fetch)

        client = RedditIngestionClient(oauth=auth)

        async def fake_execute(url, params=None, headers=None, **kwargs):
            self.requests.append({"url": url, "params": dict(params or {}),
                                  "headers": dict(headers or {})})
            return _reddit_listing(["aaa"], after=None)

        parche = mock.patch.object(client, "_execute_request", fake_execute)
        parche.start()
        self.addCleanup(parche.stop)
        return client

    def test_anonymous_client_fails_instead_of_using_the_public_endpoint(self):
        # AUD-003: sin credenciales se falla antes de salir a la red; ya no
        # se cae al endpoint publico .json con cabeceras de navegador.
        client = self._client(with_auth=False)
        with self.assertRaises(RedditCredentialsMissing):
            asyncio.run(client.fetch_subreddit_page("SaaS", limit=1))
        self.assertEqual(self.requests, [])

    def test_authenticated_client_uses_the_oauth_endpoint(self):
        client = self._client(with_auth=True)
        asyncio.run(client.fetch_subreddit_page("SaaS", limit=1))
        self.assertIn("oauth.reddit.com", self.requests[0]["url"])
        self.assertFalse(self.requests[0]["url"].endswith(".json"))

    def test_authenticated_request_carries_the_bearer_token(self):
        client = self._client(with_auth=True)
        asyncio.run(client.fetch_subreddit_page("SaaS", limit=1))
        self.assertEqual(
            self.requests[0]["headers"].get("Authorization"), "bearer tok_abc"
        )

    def test_authenticated_payload_is_parsed_the_same_way(self):
        client = self._client(with_auth=True)
        posts, cursor = asyncio.run(client.fetch_subreddit_page("SaaS", limit=1))
        self.assertEqual(posts[0].id, "aaa")
        self.assertIsNone(cursor)


if __name__ == "__main__":
    unittest.main()
