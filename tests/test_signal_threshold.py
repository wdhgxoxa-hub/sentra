"""
Corte de señal y corte de oportunidad, cada uno en su sitio (AUD-018)
=====================================================================

El pipeline de producción aplicaba a cada mensaje suelto el corte de 60 que
corresponde a un problema consolidado. Una señal individual tiene un techo
aritmético de 60 (spread y frequency clavados en 0.2), así que no cualificaba
nada. Estos tests usan los valores POR DEFECTO de producción: ningún corte
fijado a mano.
"""

import unittest

from core.intelligence import OpportunityMetrics, TemporalScorer
from core.orchestration import state


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


if __name__ == "__main__":
    unittest.main()
