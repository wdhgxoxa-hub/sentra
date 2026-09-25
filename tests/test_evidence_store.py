"""
Persistencia de evidencia multifuente (F2.3)
============================================

`PostgresStore.upsert_evidence` guarda `EvidenceItem` de cualquier fuente en
`evidence_items`: upsert idempotente por id global, interacción normalizada
en columnas y métricas nativas en JSON. La procedencia de una fila ya
guardada no cambia, y el autor solo llega como hash.
"""

import unittest
from datetime import UTC, datetime
from typing import ClassVar

from core.evidence.author import author_hash
from core.evidence.model import Engagement, EvidenceItem
from core.storage.postgres_store import PostgresStore, run_async
from tests._ayudas import presente
from tests._postgres import ADMIN_DSN, borrar_base_de_prueba, postgres_available

TEST_DB = "rir_evidence_store_test"
SAL = "2b" * 32
AHORA = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def item(nativo="42", texto="I export invoices by hand every week", **cambios):
    base = {
        "id": f"stackexchange:{nativo}", "source": "stackexchange", "community": "superuser/[excel]",
        "kind": "question", "title": "How to automate invoice exports?", "text": texto,
        "url": f"https://superuser.com/q/{nativo}", "author_hash": author_hash("stackexchange", "u1", SAL),
        "created_at": AHORA, "fetched_at": AHORA, "language": "en", "thread_id": f"stackexchange:{nativo}",
        "engagement": Engagement(score=12, replies=0, views=4500),
        "native_metrics": {"is_answered": False, "view_count": 4500}, "data_source": "real",
    }
    base.update(cambios)
    return EvidenceItem(**base)


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestUpsertEvidence(unittest.TestCase):
    dsn: ClassVar[str]

    @classmethod
    def setUpClass(cls):
        import psycopg

        from scripts.migrate import migrate

        borrar_base_de_prueba(TEST_DB)
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        cls.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")
        from pathlib import Path

        migrate(cls.dsn, Path(__file__).resolve().parents[1] / "sql" / "migrations")

    @classmethod
    def tearDownClass(cls):
        borrar_base_de_prueba(TEST_DB)

    def guardar(self, *items, run_id=None):
        async def main():
            async with PostgresStore(dsn=self.dsn) as store:
                return await store.upsert_evidence(list(items), run_id=run_id)

        return run_async(main())

    def fila(self, evidence_id):
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            return conn.execute(
                "SELECT * FROM radar.evidence_items WHERE id = %s", (evidence_id,)
            ).fetchone()

    def test_guarda_con_interaccion_normalizada_y_metricas_nativas(self):
        self.assertEqual(self.guardar(item()), 1)
        fila = self.fila("stackexchange:42")
        self.assertEqual((fila["source"], fila["kind"], fila["community"]),
                         ("stackexchange", "question", "superuser/[excel]"))
        self.assertEqual((fila["score"], fila["replies"], fila["views"], fila["reactions"]),
                         (12, 0, 4500, None))
        self.assertEqual(fila["native_metrics"], {"is_answered": False, "view_count": 4500})
        self.assertEqual(fila["data_source"], "real")
        self.assertEqual(len(fila["content_hash"]), 64)

    def test_es_idempotente_y_actualiza_lo_que_cambia(self):
        self.guardar(item("7"))
        self.guardar(item("7", engagement=Engagement(score=30, replies=2, views=9000)))
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            n = presente(conn.execute(
                "SELECT count(*) FROM radar.evidence_items WHERE id = 'stackexchange:7'"
            ).fetchone())[0]
        self.assertEqual(n, 1)
        self.assertEqual(self.fila("stackexchange:7")["score"], 30)

    def test_la_procedencia_de_una_fila_guardada_no_cambia(self):
        self.guardar(item("8", data_source="real"))
        self.guardar(item("8", data_source="demo"))
        self.assertEqual(self.fila("stackexchange:8")["data_source"], "real")

    def test_el_mismo_texto_da_la_misma_huella(self):
        self.guardar(item("9", texto="Same  TEXT here"), item("10", texto="same text here"))
        self.assertEqual(self.fila("stackexchange:9")["content_hash"],
                         self.fila("stackexchange:10")["content_hash"])

    def test_sin_items_no_hace_nada(self):
        self.assertEqual(self.guardar(), 0)

    def test_guarda_los_duplicados_apuntando_a_filas_reales(self):
        from core.sources.dedup import Duplicate

        self.guardar(item("20"), item("21"), item("22"))

        async def main():
            async with PostgresStore(dsn=self.dsn) as store:
                return await store.save_duplicates([
                    Duplicate("stackexchange:21", "stackexchange:20", "fingerprint", None),
                    Duplicate("stackexchange:22", "stackexchange:20", "embedding", 0.9712),
                ])

        self.assertEqual(run_async(main()), 2)
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            filas = conn.execute(
                "SELECT duplicate_id, method, similarity FROM radar.evidence_duplicates "
                "WHERE canonical_id = 'stackexchange:20' ORDER BY duplicate_id").fetchall()
        self.assertEqual([(d, m, None if s is None else float(s)) for d, m, s in filas],
                         [("stackexchange:21", "fingerprint", None),
                          ("stackexchange:22", "embedding", 0.9712)])
        # Repetir no duplica.
        self.assertEqual(run_async(main()), 2)

    def test_purga_la_evidencia_de_una_fuente_mas_vieja_que_su_retencion(self):
        # Políticas de la API de YouTube: refrescar o borrar en 30 días.
        from datetime import timedelta

        viejo = AHORA - timedelta(days=31)
        self.guardar(item("40", source="youtube", id="youtube:v40", fetched_at=viejo),
                     item("41", source="youtube", id="youtube:v41", fetched_at=AHORA),
                     item("42", fetched_at=viejo))

        async def main():
            async with PostgresStore(dsn=self.dsn) as store:
                return await store.purge_expired_evidence("youtube", days=30, now=AHORA)

        self.assertEqual(run_async(main()), ["youtube:v40"])
        self.assertIsNone(self.fila("youtube:v40"))
        self.assertIsNotNone(self.fila("youtube:v41"), "refrescada dentro del plazo")
        self.assertIsNotNone(self.fila("stackexchange:42"), "otra fuente no se toca")

    def test_una_ejecucion_multifuente_se_marca_real(self):
        async def main():
            async with PostgresStore(dsn=self.dsn) as store:
                run_id = await store.start_run("perfil-facturas", trigger_source="multifuente",
                                               parameters={"keywords": ["invoice"]},
                                               data_source="real")
                return await store._fetchone(
                    "SELECT * FROM pipeline_runs WHERE id = %s", (run_id,))

        run = run_async(main())
        self.assertEqual((run["data_source"], run["trigger_source"]), ("real", "multifuente"))


if __name__ == "__main__":
    unittest.main()
