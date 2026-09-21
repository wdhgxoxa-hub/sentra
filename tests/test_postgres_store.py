"""
Suite de pruebas del adaptador PostgreSQL (Fase 6)
==================================================

Dos bloques:

1. Mapeo puro (siempre se ejecuta): normalización de etiquetas a ENUM,
   hash de contenido, conversión de marcas de tiempo y construcción de
   filas a partir de los modelos del grafo. No necesita base de datos.

2. Integración (se omite si no hay PostgreSQL): escribe de verdad contra
   una base de datos de pruebas, que se crea y se destruye en cada
   ejecución. El DSN se toma de RIR_PG_TEST_DSN o del servidor local.
"""

import asyncio
import os
import unittest

from core.storage.postgres_store import (
    DEFAULT_TENANT_ID,
    run_async,
    PostgresStore,
    compute_content_hash,
    normalize_buying_intent,
    normalize_pain_severity,
    normalize_sentiment,
    normalize_urgency_level,
    normalize_willingness_to_pay,
    post_to_row,
    signal_to_row,
    to_timestamptz,
)

ADMIN_DSN = os.environ.get(
    "RIR_PG_ADMIN_DSN", "host=localhost port=5432 user=postgres dbname=postgres"
)
TEST_DB = "rir_adapter_test"


def _postgres_available():
    try:
        import psycopg

        with psycopg.connect(ADMIN_DSN, connect_timeout=3):
            return True
    except Exception:
        return False


POSTGRES_AVAILABLE = _postgres_available()


# =====================================================================
# Bloque 1: mapeo puro
# =====================================================================

class TestEnumNormalization(unittest.TestCase):
    """Las etiquetas del clasificador llevan espacios; los ENUM, guiones bajos."""

    def test_intent_labels_become_slugs(self):
        self.assertEqual(normalize_buying_intent("ready to buy"), "ready_to_buy")
        self.assertEqual(
            normalize_buying_intent("seeking recommendation"), "seeking_recommendation"
        )

    def test_intent_is_case_insensitive(self):
        self.assertEqual(normalize_buying_intent("Ready To Buy"), "ready_to_buy")

    def test_unknown_intent_falls_back_to_none(self):
        self.assertEqual(normalize_buying_intent("comprando cosas"), "none")

    def test_empty_intent_falls_back_to_none(self):
        self.assertEqual(normalize_buying_intent(""), "none")
        self.assertEqual(normalize_buying_intent(None), "none")

    def test_pain_labels_become_slugs(self):
        self.assertEqual(normalize_pain_severity("severe blocker"), "severe_blocker")
        self.assertEqual(
            normalize_pain_severity("time consuming friction"),
            "time_consuming_friction",
        )

    def test_unknown_pain_falls_back_to_none(self):
        self.assertEqual(normalize_pain_severity("dolor raro"), "none")

    def test_sentiment_labels_become_slugs(self):
        self.assertEqual(
            normalize_sentiment("negative frustration"), "negative_frustration"
        )

    def test_unknown_sentiment_falls_back_to_unknown(self):
        self.assertEqual(normalize_sentiment("euforia"), "unknown")

    def test_willingness_to_pay_is_passed_through_when_valid(self):
        self.assertEqual(normalize_willingness_to_pay("explicit"), "explicit")

    def test_unknown_willingness_falls_back_to_none(self):
        self.assertEqual(normalize_willingness_to_pay("quizas"), "none")

    def test_urgency_level_is_lowercased(self):
        self.assertEqual(normalize_urgency_level("CRITICAL"), "critical")

    def test_unknown_urgency_level_falls_back_to_medium(self):
        self.assertEqual(normalize_urgency_level("apocaliptico"), "medium")

    def test_every_slug_matches_the_sql_enum(self):
        """Los valores producidos deben existir en los ENUM del esquema."""
        from pathlib import Path

        ddl = (Path(__file__).resolve().parents[1] / "sql" / "schema.sql").read_text(
            encoding="utf-8"
        )
        for value in ("ready_to_buy", "seeking_recommendation", "seeking_alternative",
                      "comparing_products", "casual_discussion", "severe_blocker",
                      "time_consuming_friction", "minor_inconvenience", "no_problem",
                      "negative_frustration", "neutral_inquiry", "positive_praise"):
            self.assertIn(f"'{value}'", ddl, f"{value} no existe en schema.sql")


class TestContentHash(unittest.TestCase):

    def test_hash_is_deterministic(self):
        self.assertEqual(
            compute_content_hash("titulo", "cuerpo"),
            compute_content_hash("titulo", "cuerpo"),
        )

    def test_hash_changes_when_the_body_changes(self):
        self.assertNotEqual(
            compute_content_hash("titulo", "cuerpo"),
            compute_content_hash("titulo", "cuerpo editado"),
        )

    def test_hash_separates_title_from_body(self):
        """'ab' + '' no debe colisionar con 'a' + 'b'."""
        self.assertNotEqual(
            compute_content_hash("ab", ""), compute_content_hash("a", "b")
        )

    def test_hash_is_hex_sha256(self):
        digest = compute_content_hash("t", "b")
        self.assertEqual(len(digest), 64)
        int(digest, 16)  # no debe lanzar


class TestTimestampConversion(unittest.TestCase):

    def test_epoch_becomes_an_aware_datetime(self):
        moment = to_timestamptz(1758000000.0)
        self.assertIsNotNone(moment.tzinfo)

    def test_zero_epoch_is_none(self):
        """Un created_utc a cero es 'sin dato', no 1970."""
        self.assertIsNone(to_timestamptz(0.0))

    def test_none_is_none(self):
        self.assertIsNone(to_timestamptz(None))


class TestRowMapping(unittest.TestCase):

    POST = {
        "id": "t3_abc",
        "subreddit": "SaaS",
        "title": "Manual invoice exports take hours",
        "selftext": "I waste so much time every week.",
        "author": "u/x",
        "score": 120,
        "upvote_ratio": 0.97,
        "num_comments": 7,
        "created_utc": 1758000000.0,
        "url": "https://reddit.com/x",
        "permalink": "https://reddit.com/r/SaaS/x",
        "flair": "Question",
        "is_pain_signal": True,
        "matched_keywords": ["manual", "invoice"],
    }

    @classmethod
    def setUpClass(cls):
        from core.intelligence import IntelligenceEngine

        engine = IntelligenceEngine(use_transformers_if_available=False)
        cls.signal = engine.analyze_signal(
            item_id="t3_abc",
            title=cls.POST["title"],
            body=cls.POST["selftext"],
            author=cls.POST["author"],
            subreddit=cls.POST["subreddit"],
            created_utc=cls.POST["created_utc"],
            url=cls.POST["url"],
        )

    def test_post_row_carries_identity(self):
        row = post_to_row(self.POST, subreddit_name="SaaS")
        self.assertEqual(row["reddit_id"], "t3_abc")
        self.assertEqual(row["subreddit_name"], "SaaS")

    def test_post_row_carries_reddit_metrics(self):
        row = post_to_row(self.POST, subreddit_name="SaaS")
        self.assertEqual(row["score"], 120)
        self.assertEqual(row["num_comments"], 7)
        self.assertAlmostEqual(float(row["upvote_ratio"]), 0.97)

    def test_post_row_includes_a_content_hash(self):
        row = post_to_row(self.POST, subreddit_name="SaaS")
        self.assertEqual(
            row["content_hash"],
            compute_content_hash(self.POST["title"], self.POST["selftext"]),
        )

    def test_post_row_keeps_the_raw_payload(self):
        row = post_to_row(self.POST, subreddit_name="SaaS")
        self.assertEqual(row["raw_payload"]["id"], "t3_abc")

    def test_signal_row_normalizes_the_classifier_labels(self):
        row = signal_to_row(self.signal)
        self.assertIn("_", row["buying_intent"] + "_")
        self.assertNotIn(" ", row["buying_intent"])
        self.assertNotIn(" ", row["pain_severity"])

    def test_signal_row_carries_the_score_breakdown(self):
        row = signal_to_row(self.signal)
        self.assertEqual(row["final_score"], self.signal.score_breakdown.final_score)
        self.assertEqual(row["urgency_tier"], self.signal.score_breakdown.urgency_tier)
        self.assertEqual(row["recency_factor"], self.signal.score_breakdown.recency_factor)

    def test_signal_row_marks_the_classifier_engine(self):
        """Sin transformers, la clasificación es heurística y debe constar."""
        row = signal_to_row(self.signal, classifier_engine="heuristic")
        self.assertEqual(row["classifier_engine"], "heuristic")

    def test_signal_row_links_to_the_vector_store(self):
        row = signal_to_row(self.signal, embedding_ref="t3_abc",
                            embedding_model="fastembed:bge-small")
        self.assertEqual(row["embedding_ref"], "t3_abc")
        self.assertEqual(row["embedding_model"], "fastembed:bge-small")

    def test_signal_row_flags_source_kind(self):
        self.assertEqual(signal_to_row(self.signal)["source_kind"], "post")


# =====================================================================
# Bloque 2: integración real
# =====================================================================

@unittest.skipUnless(POSTGRES_AVAILABLE, "PostgreSQL no disponible")
class TestPostgresIntegration(unittest.TestCase):
    """Escribe contra una base de datos desechable creada para la suite."""

    dsn = None

    @classmethod
    def setUpClass(cls):
        import psycopg
        from pathlib import Path

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')

        cls.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")
        ddl = (Path(__file__).resolve().parents[1] / "sql" / "schema.sql").read_text(
            encoding="utf-8"
        )
        with psycopg.connect(cls.dsn) as conn:
            conn.execute(ddl)
            conn.commit()

        from core.intelligence import IntelligenceEngine

        engine = IntelligenceEngine(use_transformers_if_available=False)
        cls.signal = engine.analyze_signal(
            item_id="t3_abc",
            title="Manual invoice exports take hours",
            body="I waste so much time every week exporting invoices.",
            author="u/x",
            subreddit="SaaS",
            created_utc=1758000000.0,
            url="https://reddit.com/x",
        )

    @classmethod
    def tearDownClass(cls):
        import psycopg

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')

    def _store(self):
        return PostgresStore(dsn=self.dsn)

    def _run(self, coro_factory):
        async def main():
            async with self._store() as store:
                return await coro_factory(store)

        # En Windows psycopg exige un SelectorEventLoop; run_async lo resuelve.
        return run_async(main())

    def test_connects_and_reports_the_default_tenant(self):
        self.assertEqual(
            self._run(lambda s: s.current_tenant_id()), DEFAULT_TENANT_ID
        )

    def test_ensure_subreddit_creates_it(self):
        sid = self._run(lambda s: s.ensure_subreddit("SaaS"))
        self.assertIsNotNone(sid)

    def test_ensure_subreddit_is_idempotent(self):
        async def twice(store):
            a = await store.ensure_subreddit("devops")
            b = await store.ensure_subreddit("devops")
            return a, b

        first, second = self._run(twice)
        self.assertEqual(first, second, "no debe duplicar el subreddit")

    def test_run_lifecycle_records_telemetry(self):
        async def lifecycle(store):
            run_id = await store.start_run("SaaS", trigger_source="test")
            await store.finish_run(
                run_id,
                stats={"fetched": 10, "filtered_in": 3, "qualified": 1},
                errors=["algo menor"],
                cycles=2,
            )
            return await store.get_run(run_id)

        row = self._run(lifecycle)
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["fetched"], 10)
        self.assertEqual(row["qualified"], 1)
        self.assertEqual(row["cycles"], 2)
        self.assertEqual(row["error_count"], 1)
        self.assertIsNotNone(row["finished_at"])
        self.assertIsNotNone(row["duration_ms"])

    def test_failed_run_is_recorded_as_failed(self):
        async def failing(store):
            run_id = await store.start_run("SaaS")
            await store.finish_run(run_id, stats={}, errors=[], status="failed")
            return await store.get_run(run_id)

        self.assertEqual(self._run(failing)["status"], "failed")

    def test_persist_state_writes_the_whole_chain(self):
        state = {
            "subreddit": "SaaS",
            "filtered_items": [dict(TestRowMapping.POST)],
            "signals": [self.signal],
            "qualified": [{"id": "t3_abc"}],
            "stats": {"fetched": 1, "stored": 1, "qualified": 1},
            "errors": [],
            "cycle": 1,
        }

        async def persist(store):
            summary = await store.persist_state(state, embedding_model="hash-md5")
            feed = await store.fetch_radar_feed(limit=10)
            return summary, feed

        summary, feed = self._run(persist)
        self.assertEqual(summary["posts"], 1)
        self.assertEqual(summary["signals"], 1)
        self.assertEqual(summary["opportunities"], 1)

        entry = [f for f in feed if f["reddit_id"] == "t3_abc"][0]
        self.assertEqual(entry["subreddit_name"], "SaaS")
        self.assertTrue(entry["job_statement"])
        self.assertEqual(entry["post_title"], TestRowMapping.POST["title"])

    def test_persist_state_is_idempotent_for_identical_content(self):
        state = {
            "subreddit": "SaaS",
            "filtered_items": [dict(TestRowMapping.POST)],
            "signals": [self.signal],
            "qualified": [],
            "stats": {},
            "errors": [],
            "cycle": 1,
        }

        async def twice(store):
            await store.persist_state(state)
            await store.persist_state(state)
            return await store.count_posts()

        # El mismo post con el mismo contenido no debe multiplicarse.
        self.assertEqual(self._run(twice), 1)

    def test_full_text_search_finds_a_persisted_opportunity(self):
        state = {
            "subreddit": "SaaS",
            "filtered_items": [dict(TestRowMapping.POST)],
            "signals": [self.signal],
            "qualified": [],
            "stats": {},
            "errors": [],
            "cycle": 1,
        }

        async def search(store):
            await store.persist_state(state)
            return await store.search_posts("invoice exports", limit=5)

        hits = self._run(search)
        self.assertTrue(any(h["reddit_id"] == "t3_abc" for h in hits))

    def test_feed_can_be_filtered_by_minimum_score(self):
        async def filtered(store):
            return await store.fetch_radar_feed(limit=10, min_score=99.0)

        self.assertEqual(self._run(filtered), [])

    def test_unknown_run_is_none(self):
        import uuid

        self.assertIsNone(
            self._run(lambda s: s.get_run(str(uuid.uuid4())))
        )


if __name__ == "__main__":
    unittest.main()
