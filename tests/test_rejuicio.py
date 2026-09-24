"""
Re-juicio reproducible de un escaneo guardado (AUD2-001, 6.4)
============================================================

El re-juicio real de B3.3 se hizo a mano, sin código en el repositorio.
core.judge.rejuicio lo hace igual que el escaneo: lee la evidencia canónica
del escaneo de origen (sin duplicados), sus vectores y su tema, pasa el
juez actual y lo guarda como una ejecución nueva «rejuicio» marcada como
juzgada, sin tocar el escaneo de origen. Base desechable; LLM doble.
"""

import unittest
from datetime import UTC, datetime, timedelta
from typing import ClassVar

from core.evidence.model import EvidenceItem
from core.judge.labels import InMemoryLabelCache
from core.judge.rejuicio import evidencia_de_ejecucion, rejuzgar
from core.judge.store import latest_judged_run
from core.sources.dedup import Duplicate
from core.storage.postgres_store import PostgresStore, run_async
from tests._postgres import ADMIN_DSN, postgres_available
from tests.test_judge_pipeline import QUEJA, LLMDoble

TEST_DB = "rir_rejuicio_test"
AHORA = datetime(2026, 9, 24, tzinfo=UTC)


def pieza(n, run_id, texto=None):
    return EvidenceItem(id=f"hackernews:{n}", source="hackernews", community="Ask HN", kind="post",
                        title=f"Queja {n}", text=texto or f"{QUEJA} (caso {n})",
                        url=f"https://example.com/{n}", author_hash=f"{n:064x}",
                        created_at=AHORA - timedelta(days=3), fetched_at=AHORA, language="en",
                        thread_id=f"hackernews:{n}", data_source="real", run_id=run_id)


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestRejuicio(unittest.TestCase):
    dsn: ClassVar[str]

    @classmethod
    def setUpClass(cls):
        import psycopg

        from scripts.migrate import migrate

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        cls.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")
        from pathlib import Path

        migrate(cls.dsn, Path(__file__).resolve().parents[1] / "sql" / "migrations")

    @classmethod
    def tearDownClass(cls):
        import psycopg

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')

    def _en_store(self, funcion):
        async def main():
            async with PostgresStore(dsn=self.dsn) as store:
                return await funcion(store)

        return run_async(main())

    def _sembrar(self):
        async def sembrar(store):
            origen = await store.start_run("facturas", trigger_source="multifuente", data_source="real",
                                           parameters={"name": "facturas", "keywords": ["invoice"]})
            otra = await store.start_run("otra", trigger_source="multifuente", data_source="real")
            propias = [pieza(n, origen) for n in range(1, 7)]
            duplicada = pieza(7, origen, texto=f"{QUEJA} (caso 1)")
            ajena = pieza(8, otra)
            await store.upsert_evidence([*propias, duplicada, ajena])
            await store.save_duplicates([Duplicate(duplicate_id=duplicada.id, canonical_id=propias[0].id,
                                                   method="fingerprint", similarity=None)])
            return origen, propias

        return self._en_store(sembrar)

    def test_la_evidencia_de_un_escaneo_vuelve_entera_y_sin_duplicados(self):
        origen, propias = self._sembrar()
        leidas = self._en_store(lambda store: evidencia_de_ejecucion(store, origen))
        self.assertEqual([i.id for i in leidas], [i.id for i in propias])
        self.assertEqual(leidas[0].model_dump(exclude={"native_metrics"}),
                         propias[0].model_dump(exclude={"native_metrics"}))

    def test_rejuzga_como_ejecucion_nueva_sin_tocar_el_origen(self):
        origen, propias = self._sembrar()
        vectores = {i.id: [1.0, 0.01 * n, 0.0] for n, i in enumerate(propias)}
        nueva, resumen = rejuzgar(self.dsn, origen, provider=LLMDoble(), model="m", cache=InMemoryLabelCache(),
                                  vectores=lambda ids: {k: vectores[k] for k in ids if k in vectores}, now=AHORA)

        async def leer(store):
            ejecucion = await store._fetchone(
                "SELECT trigger_source, parameters, top_n_target FROM pipeline_runs WHERE id = %s", (nueva,))
            del_origen = await store._fetchone(
                "SELECT count(*) AS n FROM niche_verdicts WHERE run_id = %s", (origen,))
            nuevos = await store._fetchall("SELECT keywords FROM niche_verdicts WHERE run_id = %s", (nueva,))
            return dict(ejecucion), del_origen["n"], nuevos, await latest_judged_run(store)

        ejecucion, del_origen, nuevos, ultima = self._en_store(leer)
        self.assertEqual(ejecucion["trigger_source"], "rejuicio")
        self.assertEqual(ejecucion["parameters"]["rejuicio_de"], origen)
        self.assertEqual(ejecucion["top_n_target"], 6)
        self.assertEqual(del_origen, 0)
        self.assertEqual(ultima, nueva)
        self.assertEqual(resumen["items"], 6)
        self.assertTrue(nuevos)
        self.assertTrue(all("invoice" not in fila["keywords"] for fila in nuevos), "el tema no nombra nichos")


if __name__ == "__main__":
    unittest.main()
