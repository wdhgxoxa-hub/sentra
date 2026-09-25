"""
Migración 017: uso y topes de Gemini
====================================

Fase 1, B4 (decisión de Walter): el presupuesto de Gemini deja de ser un
contador a mano. `llm_usage` guarda cada intento de llamada (ejecución,
modelo, propósito, tokens, resultado); `llm_budget_settings` guarda los
cuatro topes por instalación, con los valores aprobados: 20 llamadas y
500 000 tokens por escaneo, 40 llamadas y 1 000 000 tokens por día.
"""

import unittest

from tests._postgres import postgres_available
from tests.test_migracion_015 import TENANT, BaseHasta014


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestMigracion017(BaseHasta014):

    def _uso(self, **cambios):
        fila = {"model": "gemini-x", "purpose": "etiquetado", "outcome": "ok",
                "input_tokens": 10, "output_tokens": 5, "thinking_tokens": 2, **cambios}
        self._sql("INSERT INTO llm_usage (tenant_id, model, purpose, outcome, input_tokens, output_tokens, "
                  "thinking_tokens) VALUES (%s, %(model)s, %(purpose)s, %(outcome)s, %(input_tokens)s, "
                  "%(output_tokens)s, %(thinking_tokens)s)".replace("%s", "%(tenant)s", 1),
                  {"tenant": TENANT, **fila})

    def test_la_instalacion_existente_recibe_los_topes_aprobados(self):
        self.assertEqual(
            self._sql("SELECT scan_max_calls, scan_max_tokens, daily_max_calls, daily_max_tokens "
                      "FROM llm_budget_settings WHERE tenant_id = %s", (TENANT,)),
            [(20, 500_000, 40, 1_000_000)])

    def test_los_topes_no_pueden_ser_negativos(self):
        import psycopg

        with self.assertRaises(psycopg.errors.CheckViolation):
            self._sql("UPDATE llm_budget_settings SET daily_max_calls = -1")

    def test_se_guarda_cada_intento_con_su_resultado(self):
        self._uso()
        self._uso(outcome="error", input_tokens=None, output_tokens=None, thinking_tokens=None)
        self._uso(outcome="cortada", purpose="dossier", input_tokens=0, output_tokens=0, thinking_tokens=0)
        self.assertEqual(self._sql("SELECT purpose, outcome FROM llm_usage ORDER BY id"),
                         [("etiquetado", "ok"), ("etiquetado", "error"), ("dossier", "cortada")])

    def test_proposito_y_resultado_son_cerrados(self):
        import psycopg

        for cambio in ({"purpose": "inventado"}, {"outcome": "quizas"}, {"input_tokens": -1}):
            with self.subTest(cambio), self.assertRaises(psycopg.errors.CheckViolation):
                self._uso(**cambio)


if __name__ == "__main__":
    unittest.main()
