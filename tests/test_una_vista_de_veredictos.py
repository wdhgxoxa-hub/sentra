"""
Los veredictos se ven en un solo sitio: el Radar (AUD2-008, DP6 A)
==================================================================

Fuentes repetía el Top del juez entero (una página de 7.846 px con las
mismas seis tarjetas que el Radar). Dos sitios con la misma información
confunden el flujo escanear → juzgar → decidir. Desde la Fase 2 se escanea
en «Nuevo escaneo» y los veredictos solo se ven en el Radar.
"""

import re
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "ui" / "src"


class TestUnaVistaDeVeredictos(unittest.TestCase):
    def test_las_tarjetas_de_veredicto_solo_se_pintan_en_el_radar(self):
        usos = [p.relative_to(UI).as_posix() for p in UI.rglob("*.tsx")
                if re.search(r"<VerdictCard\b", p.read_text("utf-8"))]
        self.assertEqual(usos, ["views/RadarView.tsx"])

    def test_fuentes_no_pinta_veredictos_ni_escanea(self):
        """Fase 2: el escaneo vive en «Nuevo escaneo» y los veredictos en el
        Radar; Fuentes solo dice de dónde salen las quejas."""
        fuentes = (UI / "views" / "SourcesView.tsx").read_text("utf-8")
        for pieza in ("VerdictCard", "JudgePanel", "MultiscanPanel", "useTriggerMultiscan"):
            self.assertNotIn(pieza, fuentes)


if __name__ == "__main__":
    unittest.main()
