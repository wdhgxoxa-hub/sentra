"""
Clasificación honesta: «undetermined» en vez de la etiqueta extrema (AUD-005)
============================================================================

Con similitudes empatadas, `np.argmax` devolvía la PRIMERA etiqueta de la
lista, que es la más extrema ("ready to buy", "severe blocker", "negative
frustration"). Sin evidencia, la respuesta correcta es "undetermined", que
aporta cero a su componente de la puntuación.
"""

import itertools
import unittest
from pathlib import Path

from core.intelligence import IntelligenceEngine
from core.intelligence.zeroshot_nli import (
    INTENT_CANDIDATE_LABELS,
    PAIN_CANDIDATE_LABELS,
    SENTIMENT_CANDIDATE_LABELS,
    UNDETERMINED_LABEL,
    ZeroShotNLIClassifier,
)
from tests._postgres import ADMIN_DSN, postgres_available

SIN_EVIDENCIA = [
    "Happy friday everyone\nHope you all have a great weekend.",
    "Just saying hello to the sub\nNice to meet you all.",
    "Manual invoice export is broken again\nThis manual invoice export is broken.",
]


class TestReglaDeDecision(unittest.TestCase):

    def setUp(self):
        self.clf = ZeroShotNLIClassifier(use_transformers_if_available=False)

    def test_sin_evidencia_las_tres_clasificaciones_son_indeterminadas(self):
        for texto in SIN_EVIDENCIA:
            with self.subTest(texto=texto):
                self.assertEqual(self.clf.classify_buying_intent(texto).predicted_label,
                                 UNDETERMINED_LABEL)
                self.assertEqual(self.clf.classify_pain_severity(texto).predicted_label,
                                 UNDETERMINED_LABEL)
                self.assertEqual(self.clf.classify_sentiment(texto).predicted_label,
                                 UNDETERMINED_LABEL)

    def test_con_evidencia_clara_se_sigue_etiquetando(self):
        texto = "The outage is a severe blocker for our whole team."
        self.assertEqual(self.clf.classify_pain_severity(texto).predicted_label,
                         "severe blocker")

    def test_el_orden_de_las_etiquetas_no_cambia_el_resultado(self):
        textos = SIN_EVIDENCIA + [
            "The outage is a severe blocker for our whole team.",
            "It is a minor inconvenience, nothing more.",
            "We are comparing products before we decide.",
        ]
        plantilla = "The problem described by the user is a {}."
        for etiquetas in (PAIN_CANDIDATE_LABELS, INTENT_CANDIDATE_LABELS):
            for texto in textos:
                resultados = {
                    self.clf.classify(texto, list(orden), plantilla).predicted_label
                    for orden in itertools.permutations(etiquetas)
                }
                self.assertEqual(len(resultados), 1, (texto, resultados))

    def test_el_resultado_declara_el_motor_que_lo_produjo(self):
        self.assertEqual(self.clf.classify_sentiment(SIN_EVIDENCIA[0]).engine, "heuristic")

        def pipeline_doble(texto, candidate_labels, hypothesis_template):
            return {"labels": list(candidate_labels), "scores": [0.7, 0.2, 0.1][: len(candidate_labels)]}

        self.clf.hf_pipeline = pipeline_doble
        res = self.clf.classify_sentiment("cualquier texto")
        self.assertEqual(res.engine, "transformers")
        self.assertEqual(res.predicted_label, SENTIMENT_CANDIDATE_LABELS[0])

    def test_un_empate_del_modelo_tambien_es_indeterminado(self):
        def pipeline_empatado(texto, candidate_labels, hypothesis_template):
            n = len(candidate_labels)
            return {"labels": list(candidate_labels), "scores": [1.0 / n] * n}

        self.clf.hf_pipeline = pipeline_empatado
        self.assertEqual(self.clf.classify_pain_severity("x").predicted_label,
                         UNDETERMINED_LABEL)


class TestPuntuacion(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = IntelligenceEngine(use_transformers_if_available=False)

    def _senal(self, titulo, cuerpo):
        return self.engine.analyze_signal(
            item_id="t3_x", title=titulo, body=cuerpo, author="u", subreddit="SaaS",
            created_utc=1758000000.0,
        )

    def test_una_severidad_indeterminada_aporta_cero(self):
        senal = self._senal("Happy friday everyone", "Hope you all have a great weekend.")
        self.assertEqual(senal.pain_severity, UNDETERMINED_LABEL)
        self.assertEqual(senal.score_breakdown.severity_factor, 0.0)

    def test_la_senal_persiste_el_motor_real(self):
        senal = self._senal("Happy friday everyone", "Hope you all have a great weekend.")
        self.assertEqual(senal.classifier_engine, "heuristic")


TEST_DB = "rir_nli_enum_test"


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestMigracionUndetermined(unittest.TestCase):

    def test_los_tres_enum_admiten_undetermined(self):
        import psycopg

        from scripts.migrate import migrate

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")
        try:
            migrate(dsn, Path(__file__).resolve().parents[1] / "sql" / "migrations")
            with psycopg.connect(dsn) as conn:
                for tipo in ("buying_intent", "pain_severity", "sentiment_label"):
                    valores = conn.execute(
                        f"SELECT enum_range(NULL::radar.{tipo})::text[]"
                    ).fetchone()[0]
                    self.assertIn("undetermined", valores, tipo)
        finally:
            with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
                conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')


if __name__ == "__main__":
    unittest.main()
