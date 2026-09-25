"""
Migración 020: el propósito «palabras_clave» en llm_usage (Fase 2, D1)
======================================================================

Decisión de Walter (D1, opción A): Gemini propone las palabras clave del
escaneo y esa llamada cuenta para los topes como cualquier otra. El CHECK de
`llm_usage.purpose` (017) solo admitía los propósitos de entonces; registrar
la llamada como «otros» habría escondido en qué se gasta.
"""

import unittest

from tests._postgres import postgres_available
from tests.test_migracion_015 import BaseHasta014

TENANT = "00000000-0000-0000-0000-000000000001"


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestMigracion020(BaseHasta014):

    def _usar(self, proposito: str) -> None:
        self._sql("INSERT INTO llm_usage (tenant_id, model, purpose, outcome) VALUES (%s, 'm', %s, 'ok')",
                  (TENANT, proposito))

    def test_palabras_clave_es_un_proposito_valido(self):
        self._usar("palabras_clave")
        self.assertEqual(self._sql("SELECT purpose FROM llm_usage"), [("palabras_clave",)])

    def test_los_de_antes_siguen_valiendo_y_uno_inventado_no(self):
        import psycopg

        self._usar("dossier")
        with self.assertRaises(psycopg.errors.CheckViolation):
            self._usar("inventado")


if __name__ == "__main__":
    unittest.main()
