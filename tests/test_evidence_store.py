"""
Persistencia de evidencia multifuente (F2.3)
============================================

`PostgresStore.upsert_evidence` guarda `EvidenceItem` de cualquier fuente en
`evidence_items`: upsert idempotente por id global, interacción normalizada
en columnas y métricas nativas en JSON. La procedencia de una fila ya
guardada no cambia, y el autor solo llega como hash.
"""

import os
import unittest
from datetime import UTC, datetime

from core.evidence.author import author_hash
from core.evidence.model import Engagement, EvidenceItem
from core.storage.postgres_store import PostgresStore, run_async

ADMIN_DSN = os.environ.get(
    "RIR_PG_ADMIN_DSN", "host=localhost port=5432 user=postgres dbname=postgres"
)
TEST_DB = "rir_evidence_store_test"
SAL = "2b" * 32
AHORA = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


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


@unittest.skipUnless(_postgres_available(), "PostgreSQL no disponible")
class TestUpsertEvidence(unittest.TestCase):
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

    def guardar(self, *items, run_id=None):
        async def main():
            async with PostgresStore(dsn=self.dsn, author_salt=SAL) as store:
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
            n = conn.execute(
                "SELECT count(*) FROM radar.evidence_items WHERE id = 'stackexchange:7'"
            ).fetchone()[0]
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


if __name__ == "__main__":
    unittest.main()
