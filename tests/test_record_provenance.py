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

import os
import shutil
import tempfile
import unittest
from pathlib import Path

import lancedb
import pyarrow as pa

from core.ingestion.synthetic import SyntheticFetcher
from core.orchestration import RadarDependencies, RadarPipeline
from core.orchestration.graph import data_source_of
from core.orchestration.sidecar.search import hit_to_camel as _hit_to_camel
from core.storage import HashEmbedder, HybridSearchEngine, LanceDBStore
from core.storage.lancedb_store import OpportunityRecord
from scripts.backfill_lancedb_source import fuentes_por_id, rellenar_fuentes

RAIZ = Path(__file__).resolve().parents[1]
MIGRACIONES = RAIZ / "sql" / "migrations"


def almacen(ruta: Path) -> LanceDBStore:
    return LanceDBStore(db_path=str(ruta), embedder=HashEmbedder(dim=32))


class TestFuenteDelFetcher(unittest.TestCase):

    def test_el_corpus_sintetico_es_demo(self):
        self.assertEqual(data_source_of(SyntheticFetcher()), "demo")

    def test_el_fetcher_de_reddit_es_reddit(self):
        class RedditFetcher:  # el sidecar lo reconoce por el nombre de la clase
            pass

        self.assertEqual(data_source_of(RedditFetcher()), "reddit")


class TestLanceDB(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rir_fuente_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)


    def test_un_escaneo_demo_marca_cada_fila_como_demo(self):
        store = almacen(self.tmp / "lance")
        RadarPipeline(deps=RadarDependencies(
            fetcher=SyntheticFetcher(), store=store,
            search_engine=HybridSearchEngine(store=store),
        )).run_state("SaaS")
        fuentes = store._table.to_arrow().column("data_source").to_pylist()
        self.assertTrue(fuentes)
        self.assertEqual(set(fuentes), {"demo"})

    def test_la_busqueda_entrega_la_fuente_de_cada_resultado(self):
        store = almacen(self.tmp / "lance")
        store.insert_opportunities([
            OpportunityRecord(id="t3_a", text="invoice export broken", data_source="demo"),
            OpportunityRecord(id="t3_b", text="invoice export broken again"),
        ])
        buscador = HybridSearchEngine(store=store)
        hits = {h.id: h for h in buscador.search("invoice export", limit=5)}
        self.assertEqual(hits["t3_a"].data_source, "demo")
        self.assertIsNone(hits["t3_b"].data_source)
        self.assertEqual(_hit_to_camel(hits["t3_a"])["dataSource"], "demo")

    def test_una_tabla_anterior_gana_la_columna_vacia_al_abrirse(self):
        # Una tabla escrita antes de D-J: sin columna data_source.
        db = lancedb.connect(str(self.tmp / "vieja"))
        esquema = almacen(self.tmp / "molde")._get_schema()
        antiguo = pa.schema([c for c in esquema if c.name != "data_source"])
        db.create_table(LanceDBStore.TABLE_NAME, data=[{
            "id": "t3_viejo", "text": "old", "subreddit": "", "author": "",
            "score": 0, "created_utc": 0.0, "buying_intent": "none",
            "pain_severity": "none", "urgency_tier": "LOW",
            "opportunity_score": 0.0, "job_statement": "", "current_solution": "",
            "workaround_detected": False, "url": "", "vector": [0.0] * 32,
        }], schema=antiguo)

        store = almacen(self.tmp / "vieja")
        self.assertIsNone(store.get_by_id("t3_viejo")["data_source"])
        store.insert_opportunities([OpportunityRecord(id="t3_nuevo", text="x",
                                                      data_source="reddit")])
        self.assertEqual(store.get_by_id("t3_nuevo")["data_source"], "reddit")


class TestRellenoDeLanceDB(unittest.TestCase):
    """Relleno de filas anteriores cruzando con PostgreSQL."""

    def test_la_fuente_sale_de_la_senal_con_el_mismo_id(self):
        pares = [("t3_a", "demo"), ("t3_a", "demo"), ("t3_b", "reddit"), ("t3_c", None)]
        self.assertEqual(fuentes_por_id(pares), {"t3_a": "demo", "t3_b": "reddit", "t3_c": None})

    def test_si_las_ejecuciones_discrepan_no_se_elige_ninguna(self):
        self.assertEqual(fuentes_por_id([("t3_a", "demo"), ("t3_a", "reddit")]), {"t3_a": None})

    def test_una_ejecucion_sin_fuente_no_anula_a_las_que_la_tienen(self):
        self.assertEqual(fuentes_por_id([("t3_a", None), ("t3_a", "reddit")]), {"t3_a": "reddit"})

    def test_solo_rellena_lo_vacio_y_lo_que_no_se_sabe_queda_nulo(self):
        tmp = Path(tempfile.mkdtemp(prefix="rir_relleno_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        store = almacen(tmp)
        store.insert_opportunities([
            OpportunityRecord(id="t3_a", text="a"),
            OpportunityRecord(id="t3_b", text="b", data_source="reddit"),
            OpportunityRecord(id="t3_c", text="c"),
        ])
        cambiadas = rellenar_fuentes(store, {"t3_a": "demo", "t3_b": "demo", "t3_c": None})
        self.assertEqual(cambiadas, 1)
        self.assertEqual(store.get_by_id("t3_a")["data_source"], "demo")
        self.assertEqual(store.get_by_id("t3_b")["data_source"], "reddit")
        self.assertIsNone(store.get_by_id("t3_c")["data_source"])


ADMIN_DSN = os.environ.get(
    "RIR_PG_ADMIN_DSN", "host=localhost port=5432 user=postgres dbname=postgres"
)
TEST_DB = "rir_provenance_test"


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
class TestPostgres(unittest.TestCase):

    def setUp(self):
        import psycopg

        self.tmp = Path(tempfile.mkdtemp(prefix="rir_fuente_pg_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        self.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")

    def tearDown(self):
        import psycopg

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')

    def _filas(self, sql):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            return conn.execute(sql).fetchall()

    def test_tras_un_escaneo_demo_todo_registro_persistido_es_demo(self):
        from core.storage.postgres_store import PostgresStore, run_async
        from scripts.migrate import migrate

        migrate(self.dsn, MIGRACIONES)
        store = almacen(self.tmp / "lance")
        estado = RadarPipeline(deps=RadarDependencies(
            fetcher=SyntheticFetcher(), store=store,
            search_engine=HybridSearchEngine(store=store),
        )).run_state("SaaS")

        async def escribir():
            async with PostgresStore(dsn=self.dsn) as pg:
                return await pg.persist_state(estado, data_source="demo")

        run_async(escribir())
        for tabla in ("raw_posts", "analyzed_signals", "v_radar_feed"):
            fuentes = {f[0] for f in self._filas(f"SELECT data_source FROM radar.{tabla}")}
            self.assertEqual(fuentes, {"demo"}, tabla)
        salud = self._filas("SELECT last_run_data_source FROM radar.v_subreddit_health")
        self.assertEqual({f[0] for f in salud}, {"demo"})

    def test_la_migracion_hereda_la_fuente_de_la_ejecucion(self):
        from scripts.migrate import migrate

        # Esquema hasta 006, con datos escritos antes de D-J.
        anteriores = self.tmp / "hasta_006"
        anteriores.mkdir()
        for sql in sorted(MIGRACIONES.glob("00[1-6]_*.sql")):
            shutil.copy(sql, anteriores / sql.name)
        migrate(self.dsn, anteriores)
        self._sembrar_datos_anteriores()

        migrate(self.dsn, MIGRACIONES)
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

    def test_el_relleno_de_lancedb_cruza_con_postgres(self):
        from scripts.backfill_lancedb_source import leer_fuentes
        from scripts.migrate import migrate

        migrate(self.dsn, MIGRACIONES)
        self._sembrar_datos_anteriores()
        self.assertEqual(leer_fuentes(self.dsn), {"t3_demo": "demo", "t3_reddit": "reddit"})

    def _sembrar_datos_anteriores(self):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            conn.execute("SET search_path = radar, public")
            # El tenant local lo crea la migración 001.
            tid = conn.execute("SELECT id FROM tenants WHERE slug = 'local'").fetchone()[0]
            runs = {}
            for nombre, fuente in (("demo", "demo"), ("reddit", "reddit"), ("nula", None)):
                runs[nombre] = conn.execute(
                    "INSERT INTO pipeline_runs (tenant_id, subreddit_name, status, data_source) "
                    "VALUES (%s, 'SaaS', 'completed', %s) RETURNING id", (tid, fuente),
                ).fetchone()[0]
            posts = {}
            for rid, run in (("t3_demo", runs["demo"]), ("t3_reddit", runs["reddit"]),
                             ("t3_sin_run", None), ("t3_run_sin_fuente", runs["nula"])):
                posts[rid] = conn.execute(
                    "INSERT INTO raw_posts (tenant_id, run_id, reddit_id, subreddit_name, "
                    "created_utc, content_hash) VALUES (%s, %s, %s, 'SaaS', now(), %s) "
                    "RETURNING id", (tid, run, rid, rid),
                ).fetchone()[0]
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
