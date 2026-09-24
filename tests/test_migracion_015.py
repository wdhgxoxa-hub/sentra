"""
Migración 015: un grupo sin problema común no lleva puntuación
=============================================================

Decisión del usuario: los grupos que G0 descarta como mezcla («no es un
mismo problema») no se puntúan; la puntuación de sus dimensiones confundía
(61,7/100 en un grupo mezclado). `score` admite NULL y los veredictos ya
guardados con la regla 0 lo pierden; el resto conserva el suyo.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests._postgres import ADMIN_DSN, postgres_available

RAIZ = Path(__file__).resolve().parents[1]
MIGRACIONES = RAIZ / "sql" / "migrations"
TEST_DB = "rir_migracion_015_test"
TENANT = "00000000-0000-0000-0000-000000000001"


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestMigracion015(unittest.TestCase):
    def setUp(self):
        import psycopg

        from scripts.migrate import migrate

        self.tmp = Path(tempfile.mkdtemp(prefix="rir_m015_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        self.addCleanup(self._borrar_base)
        self.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")
        hasta_014 = self.tmp / "hasta_014"
        hasta_014.mkdir()
        for sql in sorted(MIGRACIONES.glob("0[01][0-9]_*.sql")):
            if int(sql.name[:3]) <= 14:
                shutil.copy(sql, hasta_014 / sql.name)
        migrate(self.dsn, hasta_014)
        self._sembrar()
        migrate(self.dsn, MIGRACIONES)

    @staticmethod
    def _borrar_base():
        import psycopg

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')

    def _sql(self, sql, params=None):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            conn.execute("SET search_path = radar, public")
            cursor = conn.execute(sql, params)
            filas = cursor.fetchall() if sql.lstrip().upper().startswith("SELECT") else None
            conn.commit()
            return filas

    def _sembrar(self):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            conn.execute("SET search_path = radar, public")
            fila = conn.execute("INSERT INTO pipeline_runs (tenant_id, subreddit_name, trigger_source, status) "
                                "VALUES (%s, 'perfil', 'manual', 'completed') RETURNING id", (TENANT,)).fetchone()
            assert fila is not None
            for clave, regla, puntos in (("mezcla", "0: no es un mismo problema (G0)", 61.7),
                                         ("nicho", "5: fallan G1, G2 o G5", 24.3)):
                conn.execute(
                    "INSERT INTO niche_verdicts (tenant_id, run_id, cluster_key, verdict, rule, score, "
                    "weights_version, labeler_version, clustering_version, gates, dimensions, member_count) "
                    "VALUES (%s, %s, %s, 'DESCARTAR', %s, %s, 'v', 'l', 'c', %s, '[]', 3)",
                    (TENANT, fila[0], clave, regla, puntos, json.dumps([{"gate": f"G{n}"} for n in range(9)])))
            conn.commit()

    def test_la_mezcla_pierde_la_puntuacion_y_el_resto_la_conserva(self):
        self.assertEqual(self._sql("SELECT cluster_key, score::float8 FROM niche_verdicts ORDER BY cluster_key"),
                         [("mezcla", None), ("nicho", 24.3)])

    def test_la_puntuacion_sigue_acotada(self):
        import psycopg

        with self.assertRaises(psycopg.errors.CheckViolation):
            self._sql("UPDATE niche_verdicts SET score = 101 WHERE cluster_key = 'nicho'")


if __name__ == "__main__":
    unittest.main()
