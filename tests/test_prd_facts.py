"""
El PRD solo afirma lo que las cifras demuestran (AUD-009)
=========================================================

Antes decía que la palabra principal «aparece en todas las quejas» y que la
segunda «acompaña siempre» a la primera, cuando `keywords` es una unión
ordenada alfabéticamente. Tampoco podía afirmar que «el resto repite el mismo
mensaje» contando solo las 5 citas guardadas, ni presentar como 0 % una
gravedad que el clasificador no pudo determinar.
"""

import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from core.intelligence import IntelligenceEngine
from core.intelligence.blueprint import build_blueprint
from core.orchestration.aggregation import build_clusters, cluster_to_dict

ABSOLUTAS = re.compile(r"\b(todas?|todos?|siempre|nunca|all|always|never)\b", re.IGNORECASE)


def _cluster(**cambios):
    base = {
        "label": "manual + invoice + export",
        "keywords": ["export", "invoice", "manual"],
        "subreddits": ["SaaS", "accounting", "smallbusiness"],
        "mention_count": 9,
        "community_count": 3,
        "final_score": 71.0,
        "urgency_tier": "HIGH",
        "severity_factor": 0.0,
        "recency_factor": 1.0,
        "paid_signal_factor": 0.5,
        "intent_type": "complaint",
        "job_statement": "",
        "current_solutions": [],
        "evidence": [
            {"quote": f"queja numero {i}", "subreddit": "SaaS", "author": f"u{i}", "url": ""}
            for i in range(5)
        ],
        "cluster_stats": {
            "mentions": 9,
            "distinct_texts": 9,
            "severity_undetermined": 9,
            "keywords": [
                {"keyword": "manual", "count": 9},
                {"keyword": "invoice", "count": 7},
                {"keyword": "export", "count": 3},
            ],
            "pairs": [
                {"a": "manual", "b": "invoice", "count": 7},
                {"a": "manual", "b": "export", "count": 3},
                {"a": "invoice", "b": "export", "count": 2},
            ],
        },
        "data_source": "reddit",
    }
    base.update(cambios)
    return base


class TestCifrasExactas(unittest.TestCase):

    def test_la_palabra_principal_es_la_mas_frecuente_con_su_cifra(self):
        md = build_blueprint(_cluster(), "es").markdown
        self.assertIn("«manual» aparece en las 9 de 9 quejas", md)
        self.assertIn("«invoice» aparece en 7 de 9 quejas", md)
        self.assertIn("coincide con «manual» en 7", md)

    def test_en_ingles_tambien_con_cifras(self):
        md = build_blueprint(_cluster(), "en").markdown
        self.assertIn("«manual» appears in 9 of 9 complaints", md)
        self.assertIn("«invoice» appears in 7 of 9 complaints", md)

    def test_ninguna_palabra_absoluta_sin_respaldo(self):
        for idioma in ("es", "en"):
            for cluster in (_cluster(), _cluster(cluster_stats={}), _cluster(evidence=[])):
                md = build_blueprint(cluster, idioma).markdown
                self.assertIsNone(ABSOLUTAS.search(md), (idioma, ABSOLUTAS.findall(md)))

    def test_sin_recuento_por_palabra_no_se_afirma_frecuencia(self):
        md = build_blueprint(_cluster(cluster_stats={}), "es").markdown
        self.assertNotIn("aparece en", md)
        self.assertIn("no hay recuento por palabra", md)

    def test_limitar_las_citas_guardadas_no_se_confunde_con_repeticion(self):
        md = build_blueprint(_cluster(), "es").markdown
        self.assertNotIn("repite el mismo mensaje", md)
        self.assertIn("9 textos distintos", md)

    def test_la_repeticion_se_afirma_solo_si_la_hay(self):
        stats = {**_cluster()["cluster_stats"], "distinct_texts": 4}
        md = build_blueprint(_cluster(cluster_stats=stats), "es").markdown
        self.assertIn("4 textos distintos", md)
        self.assertIn("repiten un texto ya contado", md)

    def test_una_gravedad_indeterminada_no_se_presenta_como_cero(self):
        md = build_blueprint(_cluster(), "es").markdown
        self.assertNotIn("gravedad media", md)
        self.assertIn("gravedad indeterminada en las 9 de 9 quejas", md)

    def test_el_pie_no_promete_mas_de_lo_que_hay(self):
        md = build_blueprint(_cluster(), "es").markdown
        self.assertNotIn("Cada cifra sale de la base de datos", md)


class TestFuenteDeLosDatos(unittest.TestCase):

    def test_datos_de_demostracion_en_la_primera_linea(self):
        md = build_blueprint(_cluster(data_source="demo"), "es").markdown
        self.assertIn("DEMOSTRACIÓN", md.splitlines()[0])

    def test_datos_de_reddit_declarados(self):
        md = build_blueprint(_cluster(data_source="reddit"), "en").markdown
        self.assertIn("Reddit", md.splitlines()[0])

    def test_la_fuente_viaja_estructurada_para_la_interfaz(self):
        doc = build_blueprint(_cluster(data_source="demo"), "es").to_dict()
        self.assertEqual(doc["dataSource"], "demo")
        self.assertTrue(doc["sourceNotice"])
        self.assertIsNone(build_blueprint(_cluster(data_source="x"), "es").to_dict()["dataSource"])

    def test_fuente_sin_registrar_no_se_da_por_real(self):
        md = build_blueprint(_cluster(data_source=None), "es").markdown
        self.assertIn("no registrada", md.splitlines()[0])


class TestEstadisticasDeLaAgregacion(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = IntelligenceEngine(use_transformers_if_available=False)

    def _senal(self, ident, sub, cuerpo):
        return self.engine.analyze_signal(
            item_id=ident, title="The export is broken", body=cuerpo, author=ident,
            subreddit=sub, created_utc=1758000000.0,
        )

    def test_los_recuentos_salen_de_todas_las_quejas(self):
        senales = [
            self._senal("a", "SaaS", "manual invoice work"),
            self._senal("b", "accounting", "manual invoice work"),
            self._senal("c", "smallbusiness", "manual work every day"),
        ]
        cluster = cluster_to_dict(build_clusters(senales)[0])
        stats = cluster["stats"]
        self.assertEqual(stats["mentions"], 3)
        self.assertEqual(stats["distinct_texts"], 2)
        recuento = {k["keyword"]: k["count"] for k in stats["keywords"]}
        self.assertEqual(recuento, {"manual": 3, "invoice": 2, "every day": 1})
        self.assertEqual(stats["keywords"][0]["keyword"], "manual")
        pares = {(p["a"], p["b"]): p["count"] for p in stats["pairs"]}
        self.assertEqual(pares[("manual", "invoice")], 2)
        self.assertEqual(stats["severity_undetermined"], 3)

    def test_cuenta_con_que_motor_se_clasifico_cada_queja(self):
        # El dossier de Gemini lo declara (AUD-017): no es lo mismo una
        # etiqueta del NLI que una de la heurística de palabras.
        senales = [self._senal("a", "SaaS", "manual invoice work"),
                   self._senal("b", "SaaS", "manual invoice work again")]
        senales[1].classifier_engine = "transformers"
        stats = cluster_to_dict(build_clusters(senales)[0])["stats"]
        self.assertEqual(stats["classifier_engines"], {"heuristic": 1, "transformers": 1})


ADMIN_DSN = os.environ.get(
    "RIR_PG_ADMIN_DSN", "host=localhost port=5432 user=postgres dbname=postgres"
)
TEST_DB = "rir_prd_facts_test"


def _postgres_available() -> bool:
    try:
        import psycopg

        with psycopg.connect(ADMIN_DSN, connect_timeout=3):
            return True
    except Exception:  # noqa: BLE001 - sondeo de disponibilidad del servidor de pruebas
        return False


@unittest.skipUnless(_postgres_available(), "PostgreSQL no disponible")
class TestLlegaHastaLaVista(unittest.TestCase):
    """Las estadísticas y la fuente llegan a v_opportunity_board, que es lo
    que lee Rust para pedir el PRD."""

    def test_la_vista_expone_estadisticas_y_fuente(self):
        import psycopg

        from core.ingestion.synthetic import SyntheticFetcher
        from core.orchestration import RadarDependencies, RadarPipeline
        from core.storage import HashEmbedder, HybridSearchEngine, LanceDBStore
        from core.storage.postgres_store import PostgresStore, run_async
        from scripts.migrate import migrate

        tmp = Path(tempfile.mkdtemp(prefix="rir_prd_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")
        try:
            migrate(dsn, Path(__file__).resolve().parents[1] / "sql" / "migrations")
            store = LanceDBStore(db_path=str(tmp / "lance"), embedder=HashEmbedder(dim=32))
            estado = RadarPipeline(deps=RadarDependencies(
                fetcher=SyntheticFetcher(), store=store,
                search_engine=HybridSearchEngine(store=store),
            )).run_state("SaaS")

            async def escribir():
                async with PostgresStore(dsn=dsn) as pg:
                    return await pg.persist_state(estado, data_source="demo")

            run_async(escribir())
            with psycopg.connect(dsn) as conn:
                filas = conn.execute(
                    "SELECT cluster_stats, data_source, mention_count "
                    "FROM radar.v_opportunity_board"
                ).fetchall()
            self.assertTrue(filas)
            for stats, fuente, menciones in filas:
                self.assertEqual(fuente, "demo")
                self.assertEqual(stats["mentions"], menciones)
        finally:
            with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
                conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')


if __name__ == "__main__":
    unittest.main()
