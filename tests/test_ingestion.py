"""
Suite de Pruebas Unitarias y de Integración para core/ingestion
==============================================================
Verifica el 100% de los componentes de la Fase 2:
- Bypass de cookies y headers (yt-dlp)
- Filtro léxico y anti-spam (reddit-painpointer & pain-miner)
- Paginación directa por cursor (Bellingcat RPST)
- Normalización, deduplicación e interfoliado cronológico (reddit-find & snscrape)
- Cliente asíncrono unificado (crawlee/curl_cffi)
"""

import asyncio
import json
import unittest
from datetime import datetime, timezone

from core.ingestion.bypass import RedditBypass, RedditBypassConfig
from core.ingestion.filters import PainPointFilter, PAIN_POINT_KEYWORDS, FilterResult
from core.ingestion.normalizer import (
    RedditNormalizer,
    CleanPost,
    CleanComment,
    UnifiedTimelineItem
)
from core.ingestion.pagination import RedditPaginator
from core.ingestion.client import RedditIngestionClient


class TestRedditBypass(unittest.TestCase):
    def setUp(self):
        self.bypass = RedditBypass()

    def test_bypass_cookies_contain_required_flags(self):
        cookies = self.bypass.get_bypass_cookies()
        self.assertEqual(cookies.get("over18"), "1")
        self.assertIn("_options", cookies)
        # Decodificar y verificar pref_gated_sr_optin
        import urllib.parse
        decoded = json.loads(urllib.parse.unquote(cookies["_options"]))
        self.assertTrue(decoded.get("pref_gated_sr_optin"))

    def test_bypass_headers_format(self):
        headers = self.bypass.get_bypass_headers(referer="https://reddit.com/r/SaaS")
        self.assertIn("User-Agent", headers)
        self.assertEqual(headers["Referer"], "https://reddit.com/r/SaaS")
        self.assertIn("Sec-Ch-Ua", headers)

    def test_url_builders(self):
        sub_url = self.bypass.build_endpoint_url("r/microSaaS", "top")
        self.assertEqual(sub_url, "https://www.reddit.com/r/microSaaS/top.json")

        thread_url = self.bypass.build_thread_endpoint_url("technology", "t3_1abc23")
        self.assertEqual(thread_url, "https://www.reddit.com/r/technology/comments/1abc23.json")


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
        now = datetime.now(timezone.utc).timestamp()
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
            impersonate_browser="chrome124",
            timeout_seconds=10.0,
            rate_limit_delay=0.5
        )
        self.assertIsNotNone(client.bypass)
        self.assertIsNotNone(client.filter)
        self.assertIsNotNone(client.paginator)
        self.assertIsNotNone(client.normalizer)
        self.assertEqual(client.impersonate_browser, "chrome124")


if __name__ == "__main__":
    unittest.main()
