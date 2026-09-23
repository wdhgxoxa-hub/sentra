"""
Migración 009: evidencia unificada (D-M1, D-M5, R9)
===================================================

- Crea `evidence_items`, `evidence_duplicates` y `sources_state`.
- Copia `raw_posts` y `raw_comments` a `evidence_items` con su procedencia:
  'reddit' → (reddit, real); 'demo' → (demo, demo); NULL → (legacy, NULL),
  sin inferir nada (D-M5).
- Sustituye los autores en claro de las tablas antiguas, y los del JSON de
  evidencia de los clusters, por el MISMO hash que calcula Python (R9).
- `v_radar_feed` toma título, enlace e interacción de `evidence_items`.

Con PostgreSQL real sobre una base desechable; sin servidor, se omite.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from core.evidence.author import author_hash
from scripts.migrate import MigrationError, migrate

RAIZ = Path(__file__).resolve().parents[1]
MIGRACIONES = RAIZ / "sql" / "migrations"
ADMIN_DSN = os.environ.get(
    "RIR_PG_ADMIN_DSN", "host=localhost port=5432 user=postgres dbname=postgres"
)
TEST_DB = "rir_evidence_migration_test"
SAL = "5a" * 32

#: Nombres inventados que no deben sobrevivir en claro en ninguna tabla.
AUTORES = ("ana_legado", "bruno_demo", "carla_reddit", "dario_comenta")


def _postgres_available() -> bool:
    try:
        import psycopg
    except ImportError:
        return False
    try:
        with psycopg.connect(ADMIN_DSN, connect_timeout=3):
            return True
    except psycopg.Error:
        return False


@unittest.skipUnless(_postgres_available(), "PostgreSQL no disponible")
class TestMigracion009(unittest.TestCase):
    def setUp(self):
        import psycopg

        self.tmp = Path(tempfile.mkdtemp(prefix="rir_evid_mig_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        self.addCleanup(self._borrar_base)
        self.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")

    def _borrar_base(self):
        import psycopg

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')

    def filas(self, sql, params=()):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            conn.execute("SET search_path = radar, public")
            return conn.execute(sql, params).fetchall()

    def hasta_008(self):
        anteriores = self.tmp / "hasta_008"
        anteriores.mkdir()
        for sql in sorted(MIGRACIONES.glob("00[1-8]_*.sql")):
            shutil.copy(sql, anteriores / sql.name)
        migrate(self.dsn, anteriores)

    # --- Base nueva --------------------------------------------------------------

    def test_una_base_nueva_migra_sin_sal_y_tiene_las_tablas(self):
        migrate(self.dsn, MIGRACIONES)
        tablas = {f[0] for f in self.filas(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'radar'")}
        self.assertLessEqual({"evidence_items", "evidence_duplicates", "sources_state"}, tablas)

    def test_las_restricciones_hacen_cumplir_el_contrato(self):
        import psycopg

        migrate(self.dsn, MIGRACIONES)
        malas = {
            "id sin su fuente": ("reddit:1", "hackernews", "https://x", "real", None),
            "url no https": ("hackernews:1", "hackernews", "http://x", "real", None),
            "procedencia inventada": ("hackernews:2", "hackernews", "https://x", "reddit", None),
            "autor en claro": ("hackernews:3", "hackernews", "https://x", "real", "ana"),
        }
        for motivo, (iid, fuente, url, procedencia, autor) in malas.items():
            with self.subTest(motivo), self.assertRaises(psycopg.errors.CheckViolation), \
                    psycopg.connect(self.dsn) as conn:
                conn.execute("SET search_path = radar, public")
                conn.execute(
                    "INSERT INTO evidence_items (id, tenant_id, source, community, kind, "
                    "content, url, author_hash, created_at, fetched_at, data_source, "
                    "content_hash) SELECT %s, id, %s, 'c', 'post', 'texto', %s, %s, now(), "
                    "now(), %s, 'h' FROM tenants WHERE slug = 'local'",
                    (iid, fuente, url, autor, procedencia),
                )

    def test_verificada_exige_hora_y_error_exige_codigo(self):
        import psycopg

        migrate(self.dsn, MIGRACIONES)
        for estado, hora, codigo in (("verificada", None, None), ("error", None, None)):
            with self.subTest(estado), self.assertRaises(psycopg.errors.CheckViolation), \
                    psycopg.connect(self.dsn) as conn:
                conn.execute(
                    "INSERT INTO radar.sources_state (tenant_id, source, status, "
                    "last_verified_at, error_code) SELECT id, 'hackernews', %s, %s, %s "
                    "FROM radar.tenants WHERE slug = 'local'", (estado, hora, codigo),
                )

    # --- Datos anteriores --------------------------------------------------------

    def sembrar(self):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            conn.execute("SET search_path = radar, public")
            tid = conn.execute("SELECT id FROM tenants WHERE slug = 'local'").fetchone()[0]
            runs = {}
            for nombre, fuente in (("nula", None), ("demo", "demo"), ("reddit", "reddit")):
                runs[nombre] = conn.execute(
                    "INSERT INTO pipeline_runs (tenant_id, subreddit_name, status, data_source) "
                    "VALUES (%s, 'SaaS', 'completed', %s) RETURNING id", (tid, fuente),
                ).fetchone()[0]
            posts = {}
            for rid, run, autor, enlace in (
                ("t3_leg", "nula", "ana_legado", None),
                ("t3_dem", "demo", "bruno_demo", "https://reddit.com/r/SaaS/comments/t3_dem"),
                ("t3_red", "reddit", "Carla_Reddit", "https://www.reddit.com/r/SaaS/comments/red/"),
            ):
                posts[rid] = conn.execute(
                    "INSERT INTO raw_posts (tenant_id, run_id, reddit_id, subreddit_name, title, "
                    "selftext, author, score, num_comments, created_utc, permalink, content_hash, "
                    "data_source, raw_payload) VALUES (%s, %s, %s, 'SaaS', 'Título ' || %s, "
                    "'Cuerpo del post', %s, 7, 2, now(), %s, %s, "
                    "(SELECT data_source FROM pipeline_runs WHERE id = %s), "
                    "jsonb_build_object('id', %s::text, 'author', %s::text, "
                    "'author_fullname', 't2_' || %s::text)) "
                    "RETURNING id",
                    (tid, runs[run], rid, rid, autor, enlace, rid, runs[run], rid, autor, autor),
                ).fetchone()[0]
            conn.execute(
                "INSERT INTO raw_comments (tenant_id, post_id, run_id, reddit_id, author, body, "
                "created_utc, permalink, content_hash, data_source, raw_payload) VALUES (%s, %s, "
                "%s, 't1_dem', 'dario_comenta', 'Un comentario', now(), "
                "'https://reddit.com/r/SaaS/comments/t3_dem/c/t1_dem', 'hc', 'demo', "
                "'{\"author\": \"dario_comenta\", \"body\": \"Un comentario\"}'::jsonb)",
                (tid, posts["t3_dem"], runs["demo"]),
            )
            senal = conn.execute(
                "INSERT INTO analyzed_signals (tenant_id, run_id, source_kind, post_id, reddit_id, "
                "subreddit_name, author, content, created_utc, data_source) VALUES (%s, %s, 'post', "
                "%s, 't3_dem', 'SaaS', 'bruno_demo', 'x', now(), 'demo') RETURNING id",
                (tid, runs["demo"], posts["t3_dem"]),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO opportunity_clusters (tenant_id, run_id, cluster_key, label, "
                "mention_count, community_count, final_score, opportunity_id, evidence, "
                "representative_signal_id) VALUES (%s, %s, 'k', 'k', 1, 1, 10, uuidv7(), "
                "%s::jsonb, %s)",
                (tid, runs["demo"],
                 '[{"quote": "x", "author": "bruno_demo", "subreddit": "SaaS"}, {"quote": "y"}]',
                 senal),
            )
            conn.commit()

    def test_sin_sal_y_con_autores_antiguos_la_migracion_no_sigue(self):
        self.hasta_008()
        self.sembrar()
        with self.assertRaises(MigrationError):
            migrate(self.dsn, MIGRACIONES)
        self.assertEqual(self.filas("SELECT count(*) FROM raw_posts WHERE author = 'ana_legado'"),
                         [(1,)], "nada a medias: la migración no se aplicó")

    def test_copia_con_su_procedencia_sin_inferir(self):
        self.hasta_008()
        self.sembrar()
        migrate(self.dsn, MIGRACIONES, author_salt=SAL)
        items = {f[0]: f[1:] for f in self.filas(
            "SELECT id, source, data_source, kind, community, url, thread_id FROM evidence_items")}
        self.assertEqual(items["legacy:t3_leg"][:2], ("legacy", None))
        self.assertIsNone(items["legacy:t3_leg"][4], "sin enlace no se inventa uno")
        self.assertEqual(items["demo:t3_dem"][:3], ("demo", "demo", "post"))
        self.assertEqual(items["reddit:t3_red"][:2], ("reddit", "real"))
        self.assertEqual(items["reddit:t3_red"][3], "r/SaaS")
        self.assertEqual(items["demo:t1_dem"][2], "comment")
        self.assertEqual(items["demo:t1_dem"][5], "demo:t3_dem", "el comentario va en su hilo")

    def test_el_hash_de_la_migracion_es_el_de_python(self):
        self.hasta_008()
        self.sembrar()
        migrate(self.dsn, MIGRACIONES, author_salt=SAL)
        hashes = dict(self.filas("SELECT id, author_hash FROM evidence_items"))
        self.assertEqual(hashes["legacy:t3_leg"], author_hash("legacy", "ana_legado", SAL))
        self.assertEqual(hashes["reddit:t3_red"], author_hash("reddit", "carla_reddit", SAL))
        self.assertEqual(hashes["demo:t1_dem"], author_hash("demo", "dario_comenta", SAL))

    def test_ningun_nombre_queda_en_claro_en_ninguna_tabla(self):
        self.hasta_008()
        self.sembrar()
        migrate(self.dsn, MIGRACIONES, author_salt=SAL)
        volcado = " ".join(
            str(f) for tabla in ("raw_posts", "raw_comments", "analyzed_signals",
                                 "opportunity_clusters", "evidence_items")
            for f in self.filas(f"SELECT row_to_json(t)::text FROM {tabla} t")
        ).lower()
        for autor in AUTORES:
            self.assertNotIn(autor.lower(), volcado)
        cargas = self.filas("SELECT raw_payload FROM raw_posts ORDER BY reddit_id")
        self.assertTrue(all("author" not in c and "author_fullname" not in c for (c,) in cargas))
        self.assertTrue(all("id" in c for (c,) in cargas), "el resto de la carga se conserva")
        evidencia = self.filas("SELECT evidence FROM opportunity_clusters")[0][0]
        self.assertEqual(evidencia[0]["author"], author_hash("demo", "bruno_demo", SAL))
        self.assertNotIn("author", evidencia[1], "no se añade autor donde no lo había")

    def test_el_feed_lee_titulo_y_enlace_de_evidence_items(self):
        self.hasta_008()
        self.sembrar()
        migrate(self.dsn, MIGRACIONES, author_salt=SAL)
        feed = self.filas("SELECT post_title, post_permalink, post_score, num_comments "
                          "FROM v_radar_feed")
        self.assertEqual(feed, [("Título t3_dem", "https://reddit.com/r/SaaS/comments/t3_dem", 7, 2)])

    def test_volver_a_migrar_no_hace_nada(self):
        self.hasta_008()
        self.sembrar()
        migrate(self.dsn, MIGRACIONES, author_salt=SAL)
        segunda = migrate(self.dsn, MIGRACIONES, author_salt=SAL)
        self.assertEqual(segunda["applied"], [])
        self.assertEqual(self.filas("SELECT count(*) FROM evidence_items"), [(4,)])


if __name__ == "__main__":
    unittest.main()
