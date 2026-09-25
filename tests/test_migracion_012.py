"""
Migración 012: fuera la demostración antigua y el esquema de la pipeline (AUD2-002, AUD2-016)
==========================================================================================

Base desechable: esquema hasta 011 con una evidencia real, una de la
demostración antigua (fuente `legacy`, procedencia NULL, fecha 2099) y
filas en las tablas de la pipeline antigua; después, 012. La demostración
desaparece (la interfaz la enseñaba como evidencia reciente), la
procedencia pasa a ser obligatoria para que no vuelva a entrar nada sin
ella, y el esquema antiguo (tablas, vistas y columnas que apuntaban a él)
deja de existir. Lo real se queda intacto.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from tests._postgres import ADMIN_DSN, borrar_base_de_prueba, postgres_available

RAIZ = Path(__file__).resolve().parents[1]
MIGRACIONES = RAIZ / "sql" / "migrations"
TEST_DB = "rir_migracion_012_test"
TENANT = "00000000-0000-0000-0000-000000000001"
ANTIGUAS = ("raw_posts", "raw_comments", "analyzed_signals", "jtbd_opportunities",
            "opportunity_clusters", "opportunity_cluster_signals", "cluster_validations",
            "v_radar_feed", "v_opportunity_board", "v_subreddit_health")


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestMigracion012(unittest.TestCase):
    def setUp(self):
        import psycopg

        self.tmp = Path(tempfile.mkdtemp(prefix="rir_m012_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        borrar_base_de_prueba(TEST_DB)
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        self.addCleanup(self._borrar_base)
        self.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")

        from scripts.migrate import migrate

        hasta_011 = self.tmp / "hasta_011"
        hasta_011.mkdir()
        for sql in sorted(MIGRACIONES.glob("0[01][0-9]_*.sql")):
            if int(sql.name[:3]) <= 11:
                shutil.copy(sql, hasta_011 / sql.name)
        migrate(self.dsn, hasta_011)
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
            fila = ("INSERT INTO evidence_items (id, tenant_id, source, community, kind, title, content, url, "
                    "created_at, fetched_at, data_source, content_hash) "
                    "VALUES (%s, %s, %s, 'c', 'post', 't', 'texto', %s, %s, now(), %s, %s)")
            conn.execute(fila, ("hackernews:1", TENANT, "hackernews", "https://news.ycombinator.com/item?id=1",
                                "2026-09-01", "real", "h1"))
            conn.execute(fila, ("legacy:t3_demo0", TENANT, "legacy", None, "2099-12-31", None, "h2"))
            conn.execute("INSERT INTO raw_posts (tenant_id, reddit_id, subreddit_name, title, created_utc, "
                         "content_hash) VALUES (%s, 't3_x', 'test', 'viejo', now(), 'hx')", (TENANT,))
            conn.commit()

    def test_la_demostracion_antigua_desaparece_y_lo_real_queda(self):
        self.assertEqual(self._sql("SELECT id FROM evidence_items ORDER BY id"), [("hackernews:1",)])

    def test_la_procedencia_es_obligatoria(self):
        import psycopg

        with self.assertRaises(psycopg.errors.NotNullViolation):
            self._sql("INSERT INTO evidence_items (id, tenant_id, source, community, kind, content, url, "
                      "created_at, fetched_at, content_hash) VALUES ('hackernews:2', %s, 'hackernews', 'c', "
                      "'post', 'x', 'https://x.y', now(), now(), 'h3')", (TENANT,))

    def test_sin_enlace_ya_no_entra_nada(self):
        import psycopg

        with self.assertRaises(psycopg.errors.CheckViolation):
            self._sql("INSERT INTO evidence_items (id, tenant_id, source, community, kind, content, url, "
                      "created_at, fetched_at, data_source, content_hash) VALUES ('legacy:t3_z', %s, 'legacy', "
                      "'c', 'post', 'x', NULL, now(), now(), 'real', 'h4')", (TENANT,))

    def test_el_esquema_antiguo_no_existe(self):
        existentes = {f[0] for f in self._sql(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'radar'")}
        self.assertEqual(existentes & set(ANTIGUAS), set())
        columnas = {f[0] for f in self._sql(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'radar' "
            "AND table_name = 'evidence_items'")}
        self.assertFalse({"legacy_post_id", "legacy_comment_id"} & columnas)
        self.assertLessEqual({"evidence_items", "niche_verdicts", "pipeline_runs", "sources_state"}, existentes)


if __name__ == "__main__":
    unittest.main()
