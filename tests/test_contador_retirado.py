"""
El contador manual de Gemini queda retirado (Fase 1, B4)
========================================================

Decisión de Walter: el «presupuesto de 40 llamadas» se llevaba a mano en
tasks/plan-fuentes-y-e8.md; la app no lo conocía. Ahora cada intento queda en
llm_usage. El plan se marca como obsoleto y apunta a la tabla. El histórico no
se cargó: sidecar.log no tiene fecha ni tokens por línea y el re-juicio no
escribe en él, así que no se puede probar; la interfaz dice que el historial
empieza de cero.
"""

import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


class TestContadorRetirado(unittest.TestCase):
    def test_el_plan_dice_que_su_contador_es_obsoleto_y_donde_mirar(self):
        cabecera = (RAIZ / "tasks" / "plan-fuentes-y-e8.md").read_text("utf-8")[:1500]
        self.assertIn("OBSOLETO", cabecera)
        self.assertIn("llm_usage", cabecera)

    def test_la_interfaz_dice_que_el_historial_empieza_de_cero(self):
        vista = (RAIZ / "ui" / "src" / "views" / "SettingsView.tsx").read_text("utf-8")
        self.assertIn("t.settings.budget.historyFromZero", vista)
        for idioma in ("es", "en"):
            texto = (RAIZ / "ui" / "src" / "i18n" / f"{idioma}.ts").read_text("utf-8")
            encontrado = re.search(r'historyFromZero:\s*\n?\s*"([^"]+)"', texto)
            with self.subTest(idioma=idioma):
                self.assertIsNotNone(encontrado)
                assert encontrado is not None
                self.assertIn("2026-09-25", encontrado.group(1))


if __name__ == "__main__":
    unittest.main()
