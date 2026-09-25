"""
Migración 013: fuera `subreddits` (AUD2-016, pedido por el usuario antes de E8)
==============================================================================

La tabla de la pipeline de Reddit solo seguía viva porque
`pipeline_runs.subreddit_id` la referenciaba; ningún código escribe ese id.
Base desechable: esquema hasta 012 con un subreddit y dos ejecuciones (una lo
referencia); después, 013. Tabla y columna desaparecen y las ejecuciones
quedan intactas, con su nombre (`subreddit_name`, que hoy nombra el perfil).
"""

import inspect
import shutil
import tempfile
import unittest
from pathlib import Path

from tests._postgres import ADMIN_DSN, borrar_base_de_prueba, postgres_available

RAIZ = Path(__file__).resolve().parents[1]
MIGRACIONES = RAIZ / "sql" / "migrations"
TEST_DB = "rir_migracion_013_test"
TENANT = "00000000-0000-0000-0000-000000000001"
SUB = "11111111-1111-1111-1111-111111111111"
TIPOS_RETIRADOS = ("buying_intent", "pain_severity", "sentiment_label", "signal_source",
                   "urgency_level", "urgency_tier", "validation_status", "willingness_to_pay",
                   "listing_sort", "subreddit_status")


class TestSinSubredditIdEnElCodigo(unittest.TestCase):
    def test_start_run_ya_no_recibe_subreddit_id(self):
        from core.storage.postgres_store import PostgresStore

        self.assertNotIn("subreddit_id", inspect.signature(PostgresStore.start_run).parameters)


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestMigracion013(unittest.TestCase):
    def setUp(self):
        import psycopg

        self.tmp = Path(tempfile.mkdtemp(prefix="rir_m013_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        borrar_base_de_prueba(TEST_DB)
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        self.addCleanup(self._borrar_base)
        self.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")

        from scripts.migrate import migrate

        hasta_012 = self.tmp / "hasta_012"
        hasta_012.mkdir()
        for sql in sorted(MIGRACIONES.glob("0[01][0-9]_*.sql")):
            if int(sql.name[:3]) <= 12:
                shutil.copy(sql, hasta_012 / sql.name)
        migrate(self.dsn, hasta_012)
        self._sembrar()
        migrate(self.dsn, MIGRACIONES)

    @staticmethod
    def _borrar_base():
        borrar_base_de_prueba(TEST_DB)

    def _sql(self, sql, params=None):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            conn.execute("SET search_path = radar, public")
            return conn.execute(sql, params).fetchall()

    def _sembrar(self):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            conn.execute("SET search_path = radar, public")
            conn.execute("INSERT INTO subreddits (id, tenant_id, name) VALUES (%s, %s, 'saas')", (SUB, TENANT))
            ejecucion = ("INSERT INTO pipeline_runs (tenant_id, subreddit_id, subreddit_name, trigger_source, "
                         "status) VALUES (%s, %s, %s, 'manual', 'completed')")
            conn.execute(ejecucion, (TENANT, SUB, "saas"))
            conn.execute(ejecucion, (TENANT, None, "facturas"))
            conn.commit()

    def test_la_tabla_y_la_columna_no_existen(self):
        tablas = {f[0] for f in self._sql(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'radar'")}
        self.assertNotIn("subreddits", tablas)
        columnas = {f[0] for f in self._sql(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'radar' "
            "AND table_name = 'pipeline_runs'")}
        self.assertNotIn("subreddit_id", columnas)

    def test_fuera_los_tipos_del_esquema_antiguo_y_se_quedan_los_vivos(self):
        # 8 enums huérfanos desde la 012 (sus tablas ya no existían) y los 2 de subreddits.
        tipos = {f[0] for f in self._sql(
            "SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = 'radar' AND t.typtype = 'e'")}
        self.assertEqual(tipos & set(TIPOS_RETIRADOS), set())
        self.assertLessEqual({"run_status", "top_n_reason"}, tipos)

    def test_las_ejecuciones_quedan_intactas(self):
        self.assertEqual(self._sql("SELECT subreddit_name FROM pipeline_runs ORDER BY subreddit_name"),
                         [("facturas",), ("saas",)])


if __name__ == "__main__":
    unittest.main()
