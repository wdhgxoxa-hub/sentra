"""
Corte de señal y corte de oportunidad, cada uno en su sitio (AUD-018)
=====================================================================

El pipeline de producción aplicaba a cada mensaje suelto el corte de 60 que
corresponde a un problema consolidado. Una señal individual tiene un techo
aritmético de 60 (spread y frequency clavados en 0.2), así que no cualificaba
nada. Estos tests usan los valores POR DEFECTO de producción: ningún corte
fijado a mano.
"""

import logging
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from core.ingestion.synthetic import SyntheticFetcher
from core.intelligence import OpportunityMetrics, TemporalScorer
from core.orchestration import RadarDependencies, RadarPipeline, state
from core.orchestration.mcp_server import build_tools
from core.orchestration.sidecar_server import create_app
from core.storage import HashEmbedder, HybridSearchEngine, LanceDBStore


def techo_de_una_senal() -> float:
    """Puntuación de la mejor señal suelta posible: una sola voz, en un foro,
    severidad máxima, de hoy y con disposición a pagar explícita."""
    return TemporalScorer().score(
        OpportunityMetrics(
            mention_count=1,
            community_count=1,
            average_mentions_per_community=1.0,
            average_severity=5.0,
            average_paid_signal=3.0,
            newest_age_days=0.0,
        )
    ).final_score


class TestConstantes(unittest.TestCase):

    def test_el_corte_de_senal_es_alcanzable_por_una_senal(self):
        self.assertLess(state.MIN_SIGNAL_SCORE, techo_de_una_senal())

    def test_el_corte_de_oportunidad_es_para_clusters(self):
        # Ninguna señal suelta lo supera: exige difusión o recurrencia reales.
        self.assertGreaterEqual(state.MIN_OPPORTUNITY_SCORE, techo_de_una_senal())


class TestCorteDeProduccion(unittest.TestCase):

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.tmpdir = Path(tempfile.mkdtemp(prefix="rir_corte_"))
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        store = LanceDBStore(db_path=str(self.tmpdir / "lance"), embedder=HashEmbedder(dim=32))
        self.deps = RadarDependencies(
            fetcher=SyntheticFetcher(), store=store,
            search_engine=HybridSearchEngine(store=store),
        )

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def test_el_pipeline_por_defecto_cualifica_senales_del_corpus_demo(self):
        resultado = RadarPipeline(deps=self.deps).run("SaaS", limit=25)
        self.assertTrue(resultado["qualified"], "el corte por defecto no deja pasar ninguna senal")

    def test_el_sidecar_cualifica_senales_con_su_configuracion_real(self):
        client = TestClient(create_app(insecure_dev=True, deps=self.deps, persist_default=False))
        cuerpo = client.post("/api/scan", json={"subreddit": "SaaS"}).json()
        self.assertTrue(cuerpo["qualified"])

    def test_el_servidor_mcp_cualifica_senales_con_su_configuracion_real(self):
        resultado = build_tools(self.deps)["scan_subreddit"]("SaaS")
        self.assertTrue(resultado["qualified"])


if __name__ == "__main__":
    unittest.main()
