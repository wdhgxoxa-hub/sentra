"""
Migración 018: motivos de parada (Fase 1, B4)
=============================================

Decisión de Walter: cuando una ejecución o una fuente se corta, el motivo
queda guardado. `pipeline_runs.stop_reason` dice por qué se paró la
ejecución (hoy, un tope de Gemini; su detalle ya está en la fila «cortada»
de llm_usage). `run_source_outcomes` guarda, por ejecución y fuente, cómo
terminó cada una: antes el «500 de 500 ítems» de YouTube solo viajaba a la
interfaz en el evento scan:done y se perdía.
"""

import unittest

from core.sources.scan import SourceProgress
from core.storage.postgres_store import PostgresStore, run_async
from tests._postgres import postgres_available
from tests.test_migracion_015 import BaseHasta014


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestMigracion018(BaseHasta014):

    def _run(self):
        [(run,)] = self._sql("SELECT id::text FROM pipeline_runs LIMIT 1")
        return run

    def test_las_ejecuciones_anteriores_quedan_sin_motivo(self):
        self.assertEqual(self._sql("SELECT stop_reason FROM pipeline_runs"), [(None,)])

    def test_se_guarda_como_termino_cada_fuente(self):
        run = self._run()

        async def guardar():
            async with PostgresStore(dsn=self.dsn) as store:
                return await store.save_source_outcomes(run, [
                    SourceProgress("youtube", status="done", items=419, stop_reason="source_budget_exhausted",
                                   detail="presupuesto agotado: 500 de 500 ítems", requests=21, units=318.0),
                    SourceProgress("hackernews", status="failed", error_code="source_unavailable", detail="HTTP 503"),
                ])

        self.assertEqual(run_async(guardar()), 2)
        self.assertEqual(
            self._sql("SELECT source, status, stop_reason, error_code, detail, items, requests, units::float "
                      "FROM run_source_outcomes ORDER BY source"),
            [("hackernews", "failed", None, "source_unavailable", "HTTP 503", 0, 0, 0.0),
             ("youtube", "done", "source_budget_exhausted", None, "presupuesto agotado: 500 de 500 ítems",
              419, 21, 318.0)])

    def test_el_motivo_de_parada_de_la_ejecucion(self):
        from core.judge.store import marcar_parada

        run = self._run()

        async def marcar():
            async with PostgresStore(dsn=self.dsn) as store:
                await marcar_parada(store, run, "tope_escaneo_llamadas")

        run_async(marcar())
        self.assertEqual(self._sql("SELECT stop_reason FROM pipeline_runs"), [("tope_escaneo_llamadas",)])

    def test_el_estado_de_una_fuente_es_cerrado(self):
        import psycopg

        run = self._run()
        with self.assertRaises(psycopg.errors.CheckViolation):
            self._sql("INSERT INTO run_source_outcomes (tenant_id, run_id, source, status) "
                      "VALUES ('00000000-0000-0000-0000-000000000001', %s, 'hn', 'inventado')", (run,))


if __name__ == "__main__":
    unittest.main()
