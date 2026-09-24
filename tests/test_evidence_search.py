"""
Búsqueda sobre la evidencia multifuente (D-C4)
==============================================

Dos ramas y una fusión, como la búsqueda antigua pero sobre la evidencia
nueva: la densa sale de los vectores e5 (`evidence_e5`) y la léxica de
PostgreSQL (búsqueda de texto con la configuración `simple`, que no
lematiza y sirve igual para español e inglés). Se fusionan con RRF. Cada
resultado lleva su atribución y ningún autor; los duplicados no salen.
Base desechable; datos inventados.
"""

import unittest
from datetime import UTC, datetime, timedelta
from typing import ClassVar

from core.evidence.model import EvidenceItem
from core.evidence.search import RRF_K, evidence_hits, fuse_rrf, lexical_ids
from core.storage.postgres_store import PostgresStore, run_async
from tests._postgres import ADMIN_DSN, postgres_available

TEST_DB = "rir_evidence_search_test"
AHORA = datetime(2026, 9, 1, tzinfo=UTC)


class TestFusionRrf(unittest.TestCase):
    def test_lo_que_encuentran_las_dos_ramas_sube(self):
        fusion = fuse_rrf(["a", "b", "c"], ["c", "d"])
        self.assertEqual([r.id for r in fusion], ["c", "a", "b", "d"])
        c = fusion[0]
        self.assertEqual((c.dense_rank, c.lexical_rank), (3, 1))
        self.assertAlmostEqual(c.score, 1 / (RRF_K + 3) + 1 / (RRF_K + 1))

    def test_la_rama_que_no_lo_encontro_queda_en_none(self):
        fusion = {r.id: r for r in fuse_rrf(["a"], ["b"])}
        self.assertEqual((fusion["a"].dense_rank, fusion["a"].lexical_rank), (1, None))
        self.assertEqual((fusion["b"].dense_rank, fusion["b"].lexical_rank), (None, 1))

    def test_a_igual_puntuacion_el_orden_es_estable_por_id(self):
        self.assertEqual([r.id for r in fuse_rrf(["b"], ["a"])], ["a", "b"])

    def test_sin_resultados_no_hay_nada_que_fusionar(self):
        self.assertEqual(fuse_rrf([], []), [])


def pieza(n, texto, titulo=None):
    return EvidenceItem(id=f"stackexchange:{n}", source="stackexchange", community="Stack Overflow",
                        kind="question", title=titulo, text=texto, url=f"https://example.com/q/{n}",
                        author_hash=f"{n:064x}", created_at=AHORA - timedelta(days=n),
                        fetched_at=AHORA, data_source="real")


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class VectoresDobles:
    """Como EvidenceVectorStore.similar: filas con `_distance` (coseno)."""

    def __init__(self, distancias):
        self.distancias = distancias

    def similar(self, text, limit=10):
        return [{"id": i, "_distance": d} for i, d in self.distancias[:limit]]


class TestUmbralDenso(unittest.TestCase):
    """AUD2-009: «zzzz qqqq» devolvía 20 resultados. Medido sobre la evidencia
    real (79 piezas): lo pertinente tiene su mejor acierto entre 0,235 y 0,391
    y lo ajeno entre 0,399 y 0,506; la rama densa corta en 0,395."""

    def test_la_rama_densa_no_devuelve_lo_que_no_se_parece(self):
        from core.evidence.search import MAX_DISTANCIA_DENSA, dense_ids

        self.assertEqual(MAX_DISTANCIA_DENSA, 0.395)
        vectores = VectoresDobles([("a", 0.25), ("b", 0.391), ("c", 0.399), ("d", 0.50)])
        self.assertEqual(dense_ids(vectores, "consulta", 20), ["a", "b"])

    def test_una_consulta_sin_sentido_no_encuentra_nada_por_significado(self):
        from core.evidence.search import dense_ids

        self.assertEqual(dense_ids(VectoresDobles([("x", 0.41), ("y", 0.44)]), "zzzz qqqq", 20), [])


class TestBusquedaEnLaBase(unittest.TestCase):
    dsn: ClassVar[str]

    @classmethod
    def setUpClass(cls):
        from pathlib import Path

        import psycopg

        from scripts.migrate import migrate

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        cls.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")
        migrate(cls.dsn, Path(__file__).resolve().parents[1] / "sql" / "migrations")

        from core.sources.dedup import Duplicate

        async def sembrar(store):
            await store.upsert_evidence([
                pieza(1, "Las notificaciones por correo llegan tarde", "Correo lento"),
                pieza(2, "Email notifications land in spam every day"),
                pieza(3, "Exportar facturas a CSV es un infierno"),
                pieza(4, "Email notifications land in spam every day (copia)"),
            ])
            await store.save_duplicates([Duplicate("stackexchange:4", "stackexchange:2", "fingerprint", None)])

        cls._ejecutar(sembrar)

    @classmethod
    def tearDownClass(cls):
        import psycopg

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')

    @classmethod
    def _ejecutar(cls, funcion):
        async def main():
            async with PostgresStore(dsn=cls.dsn) as store:
                return await funcion(store)

        return run_async(main())

    def test_la_rama_lexica_busca_en_titulo_y_texto_sin_duplicados(self):
        self.assertEqual(self._ejecutar(lambda s: lexical_ids(s, "correo", 10)), ["stackexchange:1"])
        self.assertEqual(self._ejecutar(lambda s: lexical_ids(s, "spam", 10)), ["stackexchange:2"])
        self.assertEqual(self._ejecutar(lambda s: lexical_ids(s, "lento", 10)), ["stackexchange:1"])

    def test_basta_un_termino_y_los_que_coinciden_con_mas_van_primero(self):
        # Observado con la evidencia real: «notification preferences» no daba
        # nada porque exigía las dos palabras en la misma pieza.
        self.assertEqual(self._ejecutar(lambda s: lexical_ids(s, "spam correo", 10)),
                         ["stackexchange:1", "stackexchange:2"])
        self.assertEqual(self._ejecutar(lambda s: lexical_ids(s, "correo lento spam", 10))[0],
                         "stackexchange:1", "dos términos de tres pesan más que uno")

    def test_el_prefijo_alcanza_plurales_y_derivadas(self):
        self.assertEqual(self._ejecutar(lambda s: lexical_ids(s, "notification", 10)), ["stackexchange:2"])
        self.assertEqual(self._ejecutar(lambda s: lexical_ids(s, "factura", 10)), ["stackexchange:3"])

    def test_una_consulta_sin_terminos_utiles_no_rompe(self):
        self.assertEqual(self._ejecutar(lambda s: lexical_ids(s, "!!!", 10)), [])

    def test_comillas_y_barras_en_la_consulta_no_rompen_la_sintaxis(self):
        consulta = "it's C:\\ruta\\x 'spam' & | ! :*"
        self.assertEqual(self._ejecutar(lambda s: lexical_ids(s, consulta, 10)), ["stackexchange:2"])

    def test_los_resultados_llevan_atribucion_y_ningun_autor(self):
        fusion = fuse_rrf(["stackexchange:4", "stackexchange:3"], ["stackexchange:1"])
        hits = self._ejecutar(lambda s: evidence_hits(s, fusion))
        self.assertEqual([h["id"] for h in hits], ["stackexchange:1", "stackexchange:3"],
                         "el duplicado no sale aunque lo encuentre la rama densa")
        primero = hits[0]
        self.assertEqual(primero["title"], "Correo lento")
        self.assertEqual(primero["attribution"], {"badge": "Stack Exchange", "site": "Stack Overflow",
                                                  "url": "https://example.com/q/1"})
        self.assertEqual((primero["dense_rank"], primero["lexical_rank"]), (None, 1))
        self.assertNotIn("author_hash", primero)


if __name__ == "__main__":
    unittest.main()
