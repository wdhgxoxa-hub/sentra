"""
Suite del adaptador PostgreSQL
==============================

Lo que el adaptador sigue haciendo tras retirar la pipeline antigua (C2):
conectarse al esquema `radar` y abrir y cerrar ejecuciones con sus
contadores. La evidencia, los duplicados y los veredictos tienen sus propias
suites (test_evidence_store, test_multiscan_persist, test_judge_store). El
mapeo de posts, señales y clusters antiguos se retiró con su escritura.

Se omite si no hay PostgreSQL. La base de pruebas se crea y se destruye en
cada ejecución, con las migraciones reales.
"""

import unittest

from core.storage.postgres_store import DEFAULT_TENANT_ID, PostgresStore, run_async
from tests._postgres import ADMIN_DSN, borrar_base_de_prueba, postgres_available

TEST_DB = "rir_adapter_test"


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestPostgresIntegration(unittest.TestCase):
    """Escribe contra una base de datos desechable creada para la suite."""

    dsn = None

    @classmethod
    def setUpClass(cls):
        from pathlib import Path

        import psycopg

        borrar_base_de_prueba(TEST_DB)
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        cls.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")

        # Se levanta con el gestor de migraciones, igual que en producción.
        from scripts.migrate import migrate

        migrate(cls.dsn, Path(__file__).resolve().parents[1] / "sql" / "migrations")

    @classmethod
    def tearDownClass(cls):
        borrar_base_de_prueba(TEST_DB)

    def _run(self, coro_factory):
        async def main():
            async with PostgresStore(dsn=self.dsn) as store:
                return await coro_factory(store)

        # En Windows psycopg exige un SelectorEventLoop; run_async lo resuelve.
        return run_async(main())

    @staticmethod
    async def _ejecucion(store, run_id):
        return await store._fetchone(
            "SELECT * FROM pipeline_runs WHERE id = %s AND tenant_id = %s",
            (run_id, store.tenant_id))

    def test_se_conecta_al_esquema_con_el_tenant_local(self):
        fila = self._run(lambda s: s._fetchone("SELECT id::text AS id FROM tenants WHERE id = %s",
                                               (s.tenant_id,)))
        self.assertEqual(fila["id"], DEFAULT_TENANT_ID)

    def test_una_ejecucion_registra_sus_contadores(self):
        async def ciclo(store):
            run_id = await store.start_run("perfil", trigger_source="multifuente",
                                           data_source="real", parameters={"topic": "x"})
            await store.finish_run(run_id, stats={"fetched": 10, "stored": 7},
                                   errors=["algo menor"])
            return await self._ejecucion(store, run_id)

        fila = self._run(ciclo)
        self.assertEqual((fila["status"], fila["fetched"], fila["stored"]), ("completed", 10, 7))
        self.assertEqual((fila["trigger_source"], fila["data_source"]), ("multifuente", "real"))
        self.assertEqual(fila["error_count"], 1)
        self.assertIsNotNone(fila["finished_at"])
        self.assertIsNotNone(fila["duration_ms"])

    def test_una_ejecucion_fallida_queda_como_fallida(self):
        async def fallida(store):
            run_id = await store.start_run("perfil")
            await store.finish_run(run_id, stats={}, errors=[], status="failed")
            return await self._ejecucion(store, run_id)

        self.assertEqual(self._run(fallida)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
