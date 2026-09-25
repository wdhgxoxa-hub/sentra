"""
Procedencia por registro (AUD-016, decisión D-J)
================================================

Cada registro persistido sabe si viene de la demostración o de Reddit:
posts, comentarios y señales en PostgreSQL, y cada fila de LanceDB. Antes
solo lo sabía la ejecución, y cualquier consulta que no pasara por ella (el
feed, la búsqueda) mezclaba fuentes sin decirlo.

Las filas anteriores heredan la fuente de su ejecución (migración 007) o,
en LanceDB, de la señal con el mismo id en PostgreSQL. Si no hay forma de
saberla, queda NULL: la interfaz la enseña como «desconocida».
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from tests._ayudas import presente
from tests._postgres import ADMIN_DSN, borrar_base_de_prueba, postgres_available

RAIZ = Path(__file__).resolve().parents[1]
MIGRACIONES = RAIZ / "sql" / "migrations"


TEST_DB = "rir_provenance_test"


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestPostgres(unittest.TestCase):

    def setUp(self):
        import psycopg

        self.tmp = Path(tempfile.mkdtemp(prefix="rir_fuente_pg_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        borrar_base_de_prueba(TEST_DB)
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        self.addCleanup(self._borrar_base)
        self.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")

    @staticmethod
    def _borrar_base():
        borrar_base_de_prueba(TEST_DB)

    def _filas(self, sql):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            return conn.execute(sql).fetchall()

    def migraciones_011(self):
        """Migraciones hasta la 011: este test prueba migraciones históricas
        (007 y 009) y lee tablas que la 012 retira (AUD2-016)."""
        destino = self.tmp / "hasta_011"
        if not destino.exists():
            destino.mkdir()
            for sql in sorted(MIGRACIONES.glob("*.sql")):
                if int(sql.name[:3]) <= 11:
                    shutil.copy(sql, destino / sql.name)
        return destino

    def test_la_migracion_hereda_la_fuente_de_la_ejecucion(self):
        from scripts.migrate import migrate

        # Esquema hasta 006, con datos escritos antes de D-J.
        anteriores = self.tmp / "hasta_006"
        anteriores.mkdir()
        for sql in sorted(MIGRACIONES.glob("00[1-6]_*.sql")):
            shutil.copy(sql, anteriores / sql.name)
        migrate(self.dsn, anteriores)
        self._sembrar_datos_anteriores()

        migrate(self.dsn, self.migraciones_011())
        fuentes = dict(self._filas(
            "SELECT reddit_id, data_source FROM radar.raw_posts"))
        self.assertEqual(fuentes, {"t3_demo": "demo", "t3_reddit": "reddit",
                                   "t3_sin_run": None, "t3_run_sin_fuente": None})
        senales = dict(self._filas(
            "SELECT reddit_id, data_source FROM radar.analyzed_signals"))
        self.assertEqual(senales, {"t3_demo": "demo", "t3_reddit": "reddit"})
        comentarios = dict(self._filas(
            "SELECT reddit_id, data_source FROM radar.raw_comments"))
        self.assertEqual(comentarios, {"t1_demo": "demo"})

    def _sembrar_datos_anteriores(self):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            conn.execute("SET search_path = radar, public")
            # El tenant local lo crea la migración 001.
            tid = presente(conn.execute("SELECT id FROM tenants WHERE slug = 'local'").fetchone())[0]
            runs = {}
            for nombre, fuente in (("demo", "demo"), ("reddit", "reddit"), ("nula", None)):
                runs[nombre] = presente(conn.execute(
                    "INSERT INTO pipeline_runs (tenant_id, subreddit_name, status, data_source) "
                    "VALUES (%s, 'SaaS', 'completed', %s) RETURNING id", (tid, fuente),
                ).fetchone())[0]
            posts = {}
            for rid, run in (("t3_demo", runs["demo"]), ("t3_reddit", runs["reddit"]),
                             ("t3_sin_run", None), ("t3_run_sin_fuente", runs["nula"])):
                posts[rid] = presente(conn.execute(
                    "INSERT INTO raw_posts (tenant_id, run_id, reddit_id, subreddit_name, "
                    "created_utc, content_hash) VALUES (%s, %s, %s, 'SaaS', now(), %s) "
                    "RETURNING id", (tid, run, rid, rid),
                ).fetchone())[0]
            for rid, run in (("t3_demo", runs["demo"]), ("t3_reddit", runs["reddit"])):
                conn.execute(
                    "INSERT INTO analyzed_signals (tenant_id, run_id, source_kind, post_id, "
                    "reddit_id, subreddit_name, content, created_utc) "
                    "VALUES (%s, %s, 'post', %s, %s, 'SaaS', 'x', now())",
                    (tid, run, posts[rid], rid),
                )
            conn.execute(
                "INSERT INTO raw_comments (tenant_id, post_id, run_id, reddit_id, "
                "created_utc, content_hash) VALUES (%s, %s, %s, 't1_demo', now(), 'h')",
                (tid, posts["t3_demo"], runs["demo"]),
            )
            conn.commit()


if __name__ == "__main__":
    unittest.main()
