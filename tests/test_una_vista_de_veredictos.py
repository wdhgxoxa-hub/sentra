"""
Los veredictos se ven en un solo sitio: el Radar (AUD2-008, DP6 A)
==================================================================

Fuentes repetía el Top del juez entero (una página de 7.846 px con las
mismas seis tarjetas que el Radar). Dos sitios con la misma información
confunden el flujo escanear → juzgar → decidir. Fuentes muestra el estado
del juez tras el escaneo y un resumen con enlace al Radar.
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

    def test_fuentes_enlaza_al_radar(self):
        panel = (UI / "components" / "JudgePanel.tsx").read_text("utf-8")
        self.assertIn('setView("radar")', panel)


if __name__ == "__main__":
    unittest.main()
