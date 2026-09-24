"""
Top 6 del juez desde el sidecar (F3.8/F3.9)
===========================================

GET /api/judge/top?runId=... devuelve el Top 6 de esa ejecución o, sin
runId, el de la última ejecución multifuente juzgada; en camelCase y con
la forma de JudgeTop en ui/src/types/radar.ts. La lectura de PostgreSQL es
un doble: ningún test toca la base real.
"""

import unittest
from unittest import mock

from tests.test_sidecar_config import ConfigTestCase

LEIDO = {
    "run_id": "run-1", "target": 6, "build_count": 1,
    "reason": "Solo 1 de 6 nichos pasan todas las compuertas y el abogado del diablo; el resto no se rellena.",
    "verdicts": [{
        "id": "v1", "run_id": "run-1", "opportunity_id": "o1", "cluster_key": "invoices-export#hackernews:1",
        "keywords": ["invoices"], "verdict": "CONSTRUIR", "rule": "7: pasan todas", "score": 61.5,
        "weights_version": "judge-weights-v1", "missing": [], "member_count": 3,
        "labeler_version": None, "clustering_version": "clustering-v1",
        "member_ids": ["hackernews:1"],
        "gates": [{"gate": f"G{n}", "passed": True, "value": 3, "threshold": 2,
                   "evidence_ids": ["hackernews:1"]} for n in range(1, 9)],
        "dimensions": [{"name": "frecuencia", "value": 3, "normalized": 0.1,
                        "item_ids": ["hackernews:1"], "note": None}],
        "advocate": {"verdict_before": "CONSTRUIR", "verdict_after": "CONSTRUIR",
                     "downgraded": False, "reason": None,
                     "arguments": [{"claim": "muestra pequeña", "evidence_ids": ["hackernews:1"],
                                    "severity": "menor"}], "discarded": []},
        "corroboration": {"hackernews": 3},
        "evidence": [{"id": "hackernews:1", "source": "hackernews", "excerpt": "queja inventada",
                      "created_at": "2026-09-01T00:00:00+00:00",
                      "attribution": {"badge": "Hacker News", "site": "Ask HN",
                                      "url": "https://example.com/1"}}],
    }],
    "current_versions": {"labeler": "labels-v2", "clustering": "clustering-v2",
                         "weights": "judge-weights-v1"},
}


FEED = [{"id": "hackernews:1", "source": "hackernews", "community": "Ask HN", "kind": "post",
         "title": None, "excerpt": "queja inventada", "url": "https://example.com/1",
         "created_at": "2026-09-01T00:00:00+00:00", "data_source": "real",
         "attribution": {"badge": "Hacker News", "site": "Ask HN", "url": "https://example.com/1"}}]


class TestTopDelJuez(ConfigTestCase):
    def test_devuelve_el_top_en_camel_case(self):
        from core.orchestration.sidecar import judge

        with mock.patch.object(judge, "_leer_top", return_value=LEIDO) as leer:
            cuerpo = self.client.get("/api/judge/top", params={"runId": "run-1"}).json()
        leer.assert_called_once()
        self.assertEqual(leer.call_args.args[1], "run-1")
        self.assertEqual((cuerpo["runId"], cuerpo["buildCount"]), ("run-1", 1))
        veredicto = cuerpo["verdicts"][0]
        self.assertEqual(veredicto["gates"][0]["evidenceIds"], ["hackernews:1"])
        self.assertEqual(veredicto["advocate"]["verdictAfter"], "CONSTRUIR")
        self.assertEqual(veredicto["evidence"][0]["attribution"]["badge"], "Hacker News")
        self.assertEqual(veredicto["corroboration"], {"hackernews": 3}, "los ids de fuente no se tocan")

    def test_el_resto_de_veredictos_tambien_va_en_camel_case(self):
        from core.orchestration.sidecar import judge

        leido = {**LEIDO, "rest": LEIDO["verdicts"]}
        with mock.patch.object(judge, "_leer_top", return_value=leido):
            cuerpo = self.client.get("/api/judge/top").json()
        self.assertEqual(cuerpo["rest"][0]["advocate"]["verdictAfter"], "CONSTRUIR")
        self.assertEqual(cuerpo["rest"][0]["corroboration"], {"hackernews": 3})

    def test_el_feed_de_evidencia_llega_en_camel_case_con_tope(self):
        from core.orchestration.sidecar import judge

        with mock.patch.object(judge, "_leer_feed", return_value=FEED) as leer:
            cuerpo = self.client.get("/api/evidence/recent", params={"limit": 5000}).json()
        self.assertEqual(leer.call_args.args[1], judge.FEED_MAX, "el límite se recorta, no se obedece")
        self.assertEqual(cuerpo["items"][0]["createdAt"], "2026-09-01T00:00:00+00:00")
        self.assertEqual(cuerpo["items"][0]["dataSource"], "real")

        with mock.patch.object(judge, "_leer_feed", return_value=FEED) as leer:
            self.client.get("/api/evidence/recent")
        self.assertEqual(leer.call_args.args[1], judge.FEED_DEFAULT)

    def test_sin_run_id_pide_la_ultima_juzgada(self):
        from core.orchestration.sidecar import judge

        with mock.patch.object(judge, "_leer_top", return_value=LEIDO) as leer:
            self.client.get("/api/judge/top")
        self.assertIsNone(leer.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
