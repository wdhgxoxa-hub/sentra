"""
Migración 014: los veredictos pueden llevar G0 (coherencia)
==========================================================

`niche_verdicts_gates` exigía exactamente 8 compuertas. Con G0 (¿los
problemas del grupo son el mismo?) un veredicto nuevo lleva 9; los ya
guardados siguen con 8. Cualquier otro número sigue siendo un error.
"""

import json
import unittest
from pathlib import Path

from tests._postgres import ADMIN_DSN, borrar_base_de_prueba, postgres_available

RAIZ = Path(__file__).resolve().parents[1]
TEST_DB = "rir_migracion_014_test"
TENANT = "00000000-0000-0000-0000-000000000001"


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestMigracion014(unittest.TestCase):
    def setUp(self):
        import psycopg

        from scripts.migrate import migrate

        borrar_base_de_prueba(TEST_DB)
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        self.addCleanup(self._borrar_base)
        self.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")
        migrate(self.dsn, RAIZ / "sql" / "migrations")
        with psycopg.connect(self.dsn) as conn:
            conn.execute("SET search_path = radar, public")
            fila = conn.execute("INSERT INTO pipeline_runs (tenant_id, subreddit_name, trigger_source, status) "
                                "VALUES (%s, 'perfil', 'manual', 'completed') RETURNING id", (TENANT,)).fetchone()
            conn.commit()
        assert fila is not None
        self.run_id = fila[0]

    @staticmethod
    def _borrar_base():
        borrar_base_de_prueba(TEST_DB)

    def _guardar(self, n_compuertas: int, clave: str) -> None:
        import psycopg

        compuertas = [{"gate": f"G{n}", "passed": True} for n in range(n_compuertas)]
        with psycopg.connect(self.dsn) as conn:
            conn.execute("SET search_path = radar, public")
            conn.execute(
                "INSERT INTO niche_verdicts (tenant_id, run_id, cluster_key, verdict, rule, score, "
                "weights_version, labeler_version, clustering_version, gates, dimensions, member_count) "
                "VALUES (%s, %s, %s, 'INVESTIGAR MÁS', 'r', 10, 'v', 'l', 'c', %s, '[]', 3)",
                (TENANT, self.run_id, clave, json.dumps(compuertas)))
            conn.commit()

    def test_ocho_y_nueve_compuertas_valen(self):
        self._guardar(8, "antiguo")
        self._guardar(9, "con-g0")

    def test_otro_numero_no(self):
        import psycopg

        for n in (7, 10):
            with self.subTest(n=n), self.assertRaises(psycopg.errors.CheckViolation):
                self._guardar(n, f"mal-{n}")


if __name__ == "__main__":
    unittest.main()
