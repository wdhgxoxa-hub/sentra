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
                                  vectores=lambda ids: {k: vectores[k] for k in ids if k in vectores},
                                  vectores_frase=lambda frases: {k: vectores[k] for k in frases if k in vectores},
                                  now=AHORA)

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

    def test_el_tope_de_piezas_etiquetadas_se_puede_fijar(self):
        # Escaneo sin etiquetar (0 llamadas) + re-juicio que etiqueta todo lo que
        # pasa el filtro bajo un tope duro de llamadas: el tope por defecto (300)
        # dejaba fuera el resto de un escaneo de ~600 piezas.
        origen, propias = self._sembrar()
        vectores = {i.id: [1.0, 0.01 * n, 0.0] for n, i in enumerate(propias)}
        _, resumen = rejuzgar(self.dsn, origen, provider=LLMDoble(), model="m", cache=InMemoryLabelCache(),
                              vectores=lambda ids: {k: vectores[k] for k in ids if k in vectores},
                              vectores_frase=lambda frases: {k: vectores[k] for k in frases if k in vectores},
                              now=AHORA, label_max_items=2)
        self.assertEqual((resumen["labeled"], resumen["undetermined"]), (2, {"item_budget": 4}))


class TestProveedorDelRejuicio(unittest.TestCase):
    def test_usa_la_lista_de_modelos_guardada_y_no_la_pide_otra_vez(self):
        # AUD2-019: el re-juicio resolvía el modelo con un contexto sin caché
        # en disco y listaba los modelos en Google cada vez.
        from unittest import mock

        from core import rutas
        from core.orchestration.sidecar import context, multiscan
        from scripts import rejuzgar as script

        construidos = []

        class Espia(context.SidecarContext):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                construidos.append(self)

        with mock.patch.object(context, "SidecarContext", Espia), \
                mock.patch.object(multiscan, "_proveedor_del_juez", return_value=(None, None, "sin clave")):
            script._proveedor("postgresql://x@localhost/y")
        self.assertEqual([c.cache_modelos for c in construidos], [rutas.ruta_cache_modelos_gemini()])

    def test_max_etiquetas_llega_al_juez_y_sin_el_se_usa_el_tope_por_defecto(self):
        from unittest import mock

        from core.judge.labels import MAX_ITEMS_PER_SCAN
        from scripts import rejuzgar as script

        pasados = []

        def rejuzgar_espia(*args, **kwargs):
            pasados.append(kwargs.get("label_max_items"))
            return "nueva", {}

        with mock.patch.object(script, "_proveedor", return_value=(object(), "m", None)), \
                mock.patch.object(script, "_almacen"), \
                mock.patch.object(script, "rejuzgar", rejuzgar_espia), \
                mock.patch("core.judge.store.PostgresLabelCache"), \
                mock.patch("builtins.print"):
            script.main(["--run", "r", "--dsn", "postgresql://x@localhost/y", "--max-etiquetas", "700"])
            script.main(["--run", "r", "--dsn", "postgresql://x@localhost/y"])
        self.assertEqual(pasados, [700, MAX_ITEMS_PER_SCAN])


if __name__ == "__main__":
    unittest.main()
