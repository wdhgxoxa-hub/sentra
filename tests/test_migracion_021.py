"""
Migración 021: las propuestas de escaneo (servidor MCP)
=======================================================

Claude Desktop puede leer SENTRA, pero no gastar: para escanear deja una
propuesta en `scan_requests` y SENTRA la enseña con su estimación; el escaneo
solo arranca si Walter pulsa «Lanzar» en la ventana (decisión del
2026-10-09). La tabla impone los estados y que una propuesta resuelta diga
cuándo se resolvió.
"""

import unittest

from tests._postgres import postgres_available
from tests.test_migracion_015 import BaseHasta014

TENANT = "00000000-0000-0000-0000-000000000001"


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestMigracion021(BaseHasta014):

    def _proponer(self, perfil: str = '{"name": "x", "keywords": ["café"]}', motivo: str = "porque sí") -> str:
        self._sql("INSERT INTO scan_requests (tenant_id, profile, reason) VALUES (%s, %s::jsonb, %s)",
                  (TENANT, perfil, motivo))
        return str(self._sql("SELECT id FROM scan_requests ORDER BY created_at DESC LIMIT 1")[0][0])

    def test_una_propuesta_nace_pendiente_y_sin_resolver(self):
        self._proponer()
        self.assertEqual(self._sql("SELECT status, resolved_at, run_id, origin FROM scan_requests"),
                         [("pendiente", None, None, "mcp")])

    def test_resolverla_exige_la_fecha_y_un_estado_conocido(self):
        import psycopg

        id_ = self._proponer()
        with self.assertRaises(psycopg.errors.CheckViolation):
            self._sql("UPDATE scan_requests SET status = 'descartada' WHERE id = %s", (id_,))
        with self.assertRaises(psycopg.errors.CheckViolation):
            self._sql("UPDATE scan_requests SET status = 'inventada', resolved_at = now() WHERE id = %s", (id_,))
        self._sql("UPDATE scan_requests SET status = 'descartada', resolved_at = now() WHERE id = %s", (id_,))
        self.assertEqual(self._sql("SELECT status FROM scan_requests"), [("descartada",)])

    def test_solo_una_lanzada_puede_apuntar_a_su_escaneo(self):
        import psycopg

        id_ = self._proponer()
        self._sql("INSERT INTO pipeline_runs (tenant_id, subreddit_name) VALUES (%s, 'multi')", (TENANT,))
        run_id = self._sql("SELECT id FROM pipeline_runs LIMIT 1")[0][0]
        with self.assertRaises(psycopg.errors.CheckViolation):
            self._sql("UPDATE scan_requests SET status = 'descartada', resolved_at = now(), run_id = %s "
                      "WHERE id = %s", (run_id, id_))
        self._sql("UPDATE scan_requests SET status = 'lanzada', resolved_at = now(), run_id = %s WHERE id = %s",
                  (run_id, id_))

    def test_el_perfil_es_un_objeto_y_el_motivo_corto(self):
        import psycopg

        with self.assertRaises(psycopg.errors.CheckViolation):
            self._proponer(perfil='["no", "es", "objeto"]')
        with self.assertRaises(psycopg.errors.CheckViolation):
            self._proponer(motivo="x" * 501)


if __name__ == "__main__":
    unittest.main()
