"""
Esquema y código de la pipeline antigua, retirados (AUD2-016, DP4 A)
===================================================================

Nada del producto usaba ya las tablas y vistas de la pipeline de Reddit
(raw_posts, analyzed_signals, oportunidades…), ni el almacén LanceDB de
«oportunidades» ni el script que lo rellenaba desde esas tablas. Seguían
ahí con datos de demostración y confundían a quien leía el esquema. Estos
tests impiden que vuelvan.
"""

import unittest
from pathlib import Path

import core.storage
import core.storage.lancedb_store

RAIZ = Path(__file__).resolve().parents[1]


class TestCodigoLegadoRetirado(unittest.TestCase):
    def test_no_queda_el_almacen_de_oportunidades(self):
        for modulo in (core.storage, core.storage.lancedb_store):
            self.assertFalse(hasattr(modulo, "LanceDBStore"), modulo.__name__)
            self.assertFalse(hasattr(modulo, "OpportunityRecord"), modulo.__name__)

    def test_no_queda_el_relleno_desde_las_tablas_antiguas(self):
        self.assertFalse((RAIZ / "scripts" / "backfill_lancedb_source.py").exists())

    def test_ningun_codigo_de_produccion_nombra_las_tablas_antiguas(self):
        antiguas = ("raw_posts", "raw_comments", "analyzed_signals", "jtbd_opportunities",
                    "opportunity_clusters", "opportunity_cluster_signals", "cluster_validations",
                    "v_radar_feed", "v_opportunity_board", "v_subreddit_health", "reddit_opportunities")
        culpables = []
        for carpeta in ("core", "scripts"):
            for fichero in (RAIZ / carpeta).rglob("*.py"):
                texto = fichero.read_text(encoding="utf-8")
                culpables += [f"{fichero.relative_to(RAIZ)}: {t}" for t in antiguas if t in texto]
        self.assertEqual(culpables, [])


if __name__ == "__main__":
    unittest.main()
