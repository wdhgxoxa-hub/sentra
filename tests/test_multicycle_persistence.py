"""
La cosecha de TODOS los ciclos llega a PostgreSQL (AUD-006)
===========================================================

`filtered_items` y `signals` describen la página en curso y se reemplazan en
cada vuelta. Persistir esas claves guardaba solo el último ciclo: con el
corpus de demostración (dos páginas), la primera nunca llegaba al feed.
"""

import logging
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from core.ingestion.synthetic import PAGES, SyntheticFetcher
from core.orchestration import RadarDependencies, RadarPipeline
from core.storage import HashEmbedder, HybridSearchEngine, LanceDBStore

ADMIN_DSN = os.environ.get(
    "RIR_PG_ADMIN_DSN", "host=localhost port=5432 user=postgres dbname=postgres"
)
TEST_DB = "rir_multicycle_test"


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


class ConCorpus(unittest.TestCase):

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.tmpdir = Path(tempfile.mkdtemp(prefix="rir_multiciclo_"))
        self.addCleanup(shutil.rmtree, self.tmpdir, True)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _estado(self, pages=None):
        store = LanceDBStore(db_path=str(self.tmpdir / "lance"), embedder=HashEmbedder(dim=32))
        deps = RadarDependencies(
            fetcher=SyntheticFetcher(pages), store=store,
            search_engine=HybridSearchEngine(store=store),
        )
        return RadarPipeline(deps=deps).run_state("SaaS", limit=25)


class TestCosechaAcumulada(ConCorpus):

    def test_el_estado_final_conserva_las_senales_de_todos_los_ciclos(self):
        estado = self._estado()
        self.assertEqual(estado["cycle"], 2)
        ids_por_pagina = [{p[0] for p in pagina} for pagina in PAGES]
        ids = {s.id for s in estado["all_signals"]}
        self.assertTrue(ids & ids_por_pagina[0], "faltan las senales del primer ciclo")
        self.assertTrue(ids & ids_por_pagina[1], "faltan las senales del segundo ciclo")
        self.assertEqual({i["id"] for i in estado["all_items"]}, ids)

    def test_un_post_repetido_entre_ciclos_cuenta_una_sola_vez(self):
        pagina = PAGES[0]
        estado = self._estado(pages=[pagina, pagina])
        ids = [s.id for s in estado["all_signals"]]
        self.assertEqual(len(ids), len(set(ids)))
        items = [i["id"] for i in estado["all_items"]]
        self.assertEqual(len(items), len(set(items)))


@unittest.skipUnless(_postgres_available(), "PostgreSQL no disponible")
class TestPersistenciaMulticiclo(ConCorpus):

    @classmethod
    def setUpClass(cls):
        import psycopg

        from scripts.migrate import migrate

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        cls.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")
        migrate(cls.dsn, Path(__file__).resolve().parents[1] / "sql" / "migrations")

    @classmethod
    def tearDownClass(cls):
        import psycopg

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')

    def _persistir(self, estado):
        from core.storage.postgres_store import PostgresStore, run_async

        async def escribir():
            async with PostgresStore(dsn=self.dsn) as store:
                return await store.persist_state(estado)

        return run_async(escribir())

    def _consulta(self, sql, params=()):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            return conn.execute(sql, params).fetchall()

    def test_todas_las_senales_de_todos_los_ciclos_quedan_en_postgres(self):
        estado = self._estado()
        run_id = self._persistir(estado)["run_id"]
        guardadas = {
            fila[0] for fila in self._consulta(
                "SELECT reddit_id FROM radar.analyzed_signals WHERE run_id = %s", (run_id,)
            )
        }
        self.assertEqual(guardadas, {s.id for s in estado["all_signals"]})

    def test_cada_cluster_queda_enlazado_con_todas_sus_senales(self):
        estado = self._estado()
        run_id = self._persistir(estado)["run_id"]
        filas = self._consulta(
            """
            SELECT c.cluster_key, c.mention_count, count(cs.signal_id)
            FROM radar.opportunity_clusters c
            LEFT JOIN radar.opportunity_cluster_signals cs ON cs.cluster_id = c.id
            WHERE c.run_id = %s
            GROUP BY c.id
            """,
            (run_id,),
        )
        self.assertTrue(filas)
        for clave, menciones, enlazadas in filas:
            self.assertEqual(enlazadas, menciones, clave)

    def test_repetir_el_escaneo_no_duplica_los_posts(self):
        self._persistir(self._estado())
        antes = self._consulta("SELECT count(*) FROM radar.raw_posts")[0][0]
        self._persistir(self._estado())
        self.assertEqual(self._consulta("SELECT count(*) FROM radar.raw_posts")[0][0], antes)


if __name__ == "__main__":
    unittest.main()
