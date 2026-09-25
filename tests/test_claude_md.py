"""
CLAUDE.md no se queda atrás
===========================

CLAUDE.md es lo primero que lee cualquier sesión nueva (Fase 0). Si describe
una base, unos roles o un presupuesto que ya no existen, la sesión trabaja
sobre supuestos falsos. Esta guardia comprueba lo que más cambia: la última
migración, los roles de la base, dónde queda el uso de Gemini y la regla de
no tocar la base mientras D&S Factory trabaja.
"""

import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


class TestClaudeMd(unittest.TestCase):
    def setUp(self):
        self.texto = (RAIZ / "CLAUDE.md").read_text("utf-8")

    def test_nombra_la_ultima_migracion(self):
        ultima = max(p.name[:3] for p in (RAIZ / "sql" / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
        self.assertIn(f"001…{ultima}", self.texto)

    def test_describe_lo_que_trajo_la_fase_1(self):
        for clave in ("sentra_owner", "sentra_pruebas", "llm_usage", "llm_budget_settings",
                      "run_source_outcomes", "judge_summary", "/api/scan/estimate", "D&S Factory"):
            with self.subTest(clave=clave):
                self.assertIn(clave, self.texto)

    def test_describe_lo_que_trajo_la_fase_2(self):
        """Interfaz nueva, sus guardias y cómo se enchufará el modo Videos."""
        for clave in ("Nuevo escaneo", "latest_run_with_niches", "/api/documents/status",
                      "/api/scan/keywords", "palabras_clave", "tests/_lenguaje_llano.py", "data-ajeno",
                      "Modo Videos: cómo se enchufa", "ui/src/modos/registro.ts", "SelectorDeModo"):
            with self.subTest(clave=clave):
                self.assertIn(clave, self.texto)

    def test_ya_no_dice_que_el_radar_pierde_el_nicho(self):
        self.assertNotIn("el nicho de impagos no se ve en el Radar", self.texto)

    def test_ya_no_dice_que_el_presupuesto_es_un_contador_a_mano(self):
        self.assertNotIn("La app no lo conoce, no\n  lo muestra y no lo hace cumplir", self.texto)
        self.assertNotIn("1 000 000 (`core/llm/budget.py`", self.texto)


if __name__ == "__main__":
    unittest.main()
