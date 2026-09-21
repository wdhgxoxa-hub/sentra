"""
Suite de Pruebas Unitarias y de Integración para core/intelligence
=================================================================
Verifica el 100% de los módulos de la Fase 3:
- Ponderación y decaimiento temporal exponencial (painpoint-atlas)
- Extracción de Jobs-To-Be-Done y riesgos (pain-miner)
- Clasificador local Zero-Shot NLI (reddit-sentiment-zero-shot)
- Clustering semántico y tópicos emergentes (reddit-nlp-analytics)
- Motor central unificado de inteligencia (reddit-market-analyzer)
"""

import math
import unittest
from datetime import datetime, timezone

from core.intelligence.clustering import TopicClusterer
from core.intelligence.engine import IntelligenceEngine
from core.intelligence.jtbd_analyzer import JTBDAnalyzer, TASK_BY_INTENT
from core.intelligence.temporal_scoring import OpportunityMetrics, TemporalScorer
from core.intelligence.zeroshot_nli import ZeroShotNLIClassifier


class TestTemporalScorer(unittest.TestCase):
    def setUp(self):
        self.scorer = TemporalScorer(half_life_days=180.0)

    def test_recency_exponential_decay(self):
        # 0 días -> frescura máxima (1.0)
        self.assertAlmostEqual(self.scorer.calculate_recency(0.0), 1.0, places=4)
        # 180 días (half-life) -> e^(-1) ~= 0.367879
        self.assertAlmostEqual(self.scorer.calculate_recency(180.0), math.exp(-1.0), places=4)
        # 360 días -> e^(-2) ~= 0.135335
        self.assertAlmostEqual(self.scorer.calculate_recency(360.0), math.exp(-2.0), places=4)

    def test_factor_normalizations(self):
        # Spread (5 comunidades es benchmark completo)
        self.assertEqual(self.scorer.calculate_spread(5), 1.0)
        self.assertEqual(self.scorer.calculate_spread(10), 1.0)  # capped
        self.assertEqual(self.scorer.calculate_spread(2), 0.4)

        # Severidad (1 a 5 mapea a 0 a 1)
        self.assertEqual(self.scorer.calculate_severity(1.0), 0.0)
        self.assertEqual(self.scorer.calculate_severity(5.0), 1.0)
        self.assertEqual(self.scorer.calculate_severity(3.0), 0.5)

        # Paid Signal (0 a 3 mapea a 0 a 1)
        self.assertEqual(self.scorer.calculate_paid_signal(0.0), 0.0)
        self.assertEqual(self.scorer.calculate_paid_signal(3.0), 1.0)
        self.assertEqual(self.scorer.calculate_paid_signal(1.5), 0.5)

    def test_composite_opportunity_scoring(self):
        metrics = OpportunityMetrics(
            mention_count=10,
            community_count=5,                     # spread = 1.0 (peso 0.25)
            average_mentions_per_community=5.0,     # freq = 1.0 (peso 0.25)
            average_severity=5.0,                  # sev = 1.0 (peso 0.20)
            average_paid_signal=3.0,               # paid = 1.0 (peso 0.15)
            newest_age_days=0.0                    # rec = 1.0 (peso 0.15)
        )
        res = self.scorer.score(metrics)
        self.assertEqual(res.final_score, 100.0)
        self.assertEqual(res.urgency_tier, "CRITICAL")

        # Caso con decaimiento temporal y baja severidad
        old_metrics = OpportunityMetrics(
            mention_count=2,
            community_count=1,
            average_mentions_per_community=1.0,
            average_severity=1.5,
            average_paid_signal=0.0,
            newest_age_days=360.0
        )
        old_res = self.scorer.score(old_metrics)
        self.assertLess(old_res.final_score, 30.0)
        self.assertEqual(old_res.urgency_tier, "LOW")


class TestJTBDAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = JTBDAnalyzer()

    def test_intent_classification(self):
        sample_alt = "I am looking for an alternative to Jira because it is too complex and slow."
        intent, conf = self.analyzer.classify_intent(sample_alt)
        self.assertEqual(intent, "alternative_search")
        self.assertGreater(conf, 0.5)

        sample_wtp = "I am willing to pay $100/mo for a tool that automates client invoices."
        intent_wtp, _ = self.analyzer.classify_intent(sample_wtp)
        self.assertEqual(intent_wtp, "purchase_intent")

    def test_detect_workaround(self):
        text_with_hack = "There is no native sync, so my workaround is a python script to pull data into Airtable."
        has_workaround, desc = self.analyzer.detect_workaround(text_with_hack)
        self.assertTrue(has_workaround)
        self.assertIsNotNone(desc)
        self.assertIn("python script", desc)

        clean_text = "Does this feature work out of the box?"
        has_workaround, _ = self.analyzer.detect_workaround(clean_text)
        self.assertFalse(has_workaround)

    def test_known_tool_extraction(self):
        text = "Our team is moving away from Salesforce to HubSpot."
        tool = self.analyzer.extract_current_solution(text)
        self.assertIn(tool, ["Salesforce", "Hubspot"])

    def test_risk_scanning(self):
        text_spam = "Get 50% discount with promo code SAVE50 or use ref=partner."
        risks = self.analyzer.scan_risks(text_spam)
        self.assertIn("affiliate_or_referral_pattern", risks)

    def test_analyze_post_full_jtbd(self):
        post_req = self.analyzer.analyze_post(
            post_id="p101",
            title="Stripe invoice reconciliation is broken",
            body="I am willing to pay for an automated tool because manual matching takes 10 hours every week.",
            url="https://reddit.com/r/saas/p101"
        )
        self.assertEqual(post_req.id, "jtbd_p101")
        self.assertEqual(post_req.current_solution, "Stripe")
        self.assertEqual(post_req.willingness_to_pay, "explicit")
        self.assertIn("Cuando los profesionales enfrentan", post_req.job_statement)
        self.assertEqual(post_req.urgency_level, "high")


class TestZeroShotNLIClassifier(unittest.TestCase):
    def setUp(self):
        # Utiliza motor local semántico
        self.classifier = ZeroShotNLIClassifier(use_transformers_if_available=False)

    def test_buying_intent_classification(self):
        text = "We have budget approved and are ready to buy an enterprise CRM this quarter."
        res = self.classifier.classify_buying_intent(text)
        self.assertEqual(res.predicted_label, "ready to buy")
        self.assertGreater(res.confidence, 0.20)
        self.assertIn("ready to buy", res.all_scores)

    def test_pain_severity_classification(self):
        text = "The entire server goes down during peak hours, causing a severe blocker and lost revenue."
        res = self.classifier.classify_pain_severity(text)
        self.assertEqual(res.predicted_label, "severe blocker")
        self.assertGreater(res.confidence, 0.20)

    def test_sentiment_classification(self):
        text = "Customer support was horrible, rude, and completely unhelpful. Very frustrating experience."
        res = self.classifier.classify_sentiment(text)
        self.assertEqual(res.predicted_label, "negative frustration")


class TestTopicClusterer(unittest.TestCase):
    def setUp(self):
        self.clusterer = TopicClusterer(random_state=42)

    def test_emerging_keywords_extraction(self):
        texts = [
            "We are struggling with database connection pool exhaustion on PostgreSQL.",
            "Our PostgreSQL database connection timeout happens every morning.",
            "Any recommendations for connection pooling in PostgreSQL microservices?",
            "High memory usage in docker containers running FastAPI."
        ]
        kws = self.clusterer.extract_emerging_keywords(texts, top_n=5)
        self.assertGreater(len(kws), 0)
        kw_names = [k[0] for k in kws]
        self.assertTrue(any("postgresql" in k or "connection" in k for k in kw_names))

    def test_clustering_partition(self):
        texts = [
            "PostgreSQL connection timeout error when scaling up workers",
            "PostgreSQL database connection pool limits exceeded",
            "Billing reconciliation takes hours in Stripe invoicing",
            "Stripe invoices webhook failure during subscription checkout",
            "Hiring remote engineers for Python backend roles"
        ]
        res = self.clusterer.cluster(texts, n_clusters=3)
        self.assertEqual(res.total_documents, 5)
        self.assertEqual(res.n_clusters, 3)
        self.assertEqual(len(res.clusters), 3)
        for cl in res.clusters:
            self.assertGreater(cl.size, 0)
            self.assertIsNotNone(cl.representative_text)


class TestIntelligenceEngine(unittest.TestCase):
    def setUp(self):
        self.engine = IntelligenceEngine(use_transformers_if_available=False)

    def test_analyze_signal_single(self):
        now_ts = datetime.now(timezone.utc).timestamp()
        signal = self.engine.analyze_signal(
            item_id="item_01",
            title="Need alternative to Salesforce for small team",
            body="Salesforce is way too expensive and bloated. Willing to pay for a lightweight CRM.",
            author="alex_dev",
            subreddit="SaaS",
            created_utc=now_ts,
            url="https://reddit.com/r/SaaS/item_01",
            community_count=3
        )
        self.assertEqual(signal.id, "item_01")
        self.assertEqual(signal.buying_intent, "seeking alternative")
        self.assertEqual(signal.jtbd.willingness_to_pay, "explicit")
        self.assertIn("Salesforce", signal.jtbd.current_solution)
        self.assertGreater(signal.score_breakdown.final_score, 40.0)

    def test_analyze_batch(self):
        now_ts = datetime.now(timezone.utc).timestamp()
        items = [
            {
                "id": "1",
                "title": "Stripe invoice sync fails constantly",
                "selftext": "Our accounting team spends 15 hours every week reconciling Stripe payments manually.",
                "author": "cfo_user",
                "subreddit": "fintech",
                "created_utc": now_ts - 3600
            },
            {
                "id": "2",
                "title": "Best alternative to QuickBooks for freelancers",
                "selftext": "Looking for simple invoicing software. Willing to pay $20/month.",
                "author": "designer_sam",
                "subreddit": "freelance",
                "created_utc": now_ts - 7200
            },
            {
                "id": "3",
                "title": "Launched our open source project today!",
                "selftext": "Check out our repo on github, hope you enjoy it.",
                "author": "oss_dev",
                "subreddit": "opensource",
                "created_utc": now_ts - 86400
            }
        ]

        report = self.engine.analyze_batch(items, topic_or_subreddit="Invoicing & Billing")
        self.assertEqual(report.total_signals_evaluated, 3)
        self.assertGreaterEqual(report.critical_opportunities_count, 1)
        self.assertGreater(len(report.signals), 0)
        self.assertGreater(len(report.top_jtbd_statements), 0)
        self.assertGreater(len(report.clusters.clusters), 0)


if __name__ == "__main__":
    unittest.main()
