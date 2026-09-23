"""
Vectores de evidencia multilingües (F2.3, D-M2)
===============================================

La evidencia llega en varios idiomas: el almacén de evidencia usa
intfloat/multilingual-e5-large (1024 dimensiones). e5 exige prefijos
distintos para documentos ("passage: ") y consultas ("query: "); sin ellos
las búsquedas empeoran sin que nada falle. Cada fila lleva su id global y su
fuente, y ningún autor (R9).

Los tests no descargan el modelo: se inyecta un doble con la forma de
fastembed, o se usa el embebedor por hash.
"""

import shutil
import tempfile
import unittest
import unittest.mock
from datetime import UTC, datetime

import numpy as np

from core.evidence.model import EvidenceItem
from core.evidence.vectors import EvidenceVectorStore
from core.storage.embeddings import (
    MULTILINGUAL_MODEL_NAME,
    MULTILINGUAL_VECTOR_DIM,
    FastEmbedEmbedder,
    HashEmbedder,
)

AHORA = datetime(2026, 9, 1, tzinfo=UTC)


class ModeloEspia:
    """Doble de fastembed.TextEmbedding: guarda lo que recibe."""

    def __init__(self, dim=4):
        self.dim = dim
        self.recibido: list[str] = []

    def embed(self, textos):
        self.recibido.extend(textos)
        return [np.ones(self.dim, dtype=np.float32) * (i + 1) for i in range(len(textos))]


def item(nativo, texto, fuente="hackernews", procedencia="real"):
    return EvidenceItem(
        id=f"{fuente}:{nativo}", source=fuente, community="Ask HN", kind="post",
        text=texto, url=f"https://example.com/{nativo}", author_hash=None,
        created_at=AHORA, fetched_at=AHORA, data_source=procedencia,
    )


class TestPrefijosDeE5(unittest.TestCase):
    def test_e5_usa_passage_para_documentos_y_query_para_consultas(self):
        espia = ModeloEspia()
        embebedor = FastEmbedEmbedder(MULTILINGUAL_MODEL_NAME, _modelo=espia)
        espia.recibido.clear()
        embebedor.embed_batch(["factura manual"])
        embebedor.embed_query("herramienta de facturas")
        self.assertEqual(espia.recibido, ["passage: factura manual",
                                          "query: herramienta de facturas"])

    def test_un_modelo_sin_prefijos_no_los_recibe(self):
        espia = ModeloEspia()
        embebedor = FastEmbedEmbedder("BAAI/bge-small-en-v1.5", _modelo=espia)
        espia.recibido.clear()
        embebedor.embed_query("x")
        self.assertEqual(espia.recibido, ["x"])

    def test_los_vectores_salen_normalizados(self):
        vector = FastEmbedEmbedder(MULTILINGUAL_MODEL_NAME, _modelo=ModeloEspia()).embed_query("x")
        self.assertAlmostEqual(float(np.linalg.norm(vector)), 1.0, places=5)

    def test_el_modelo_multilingue_es_el_de_d_m2(self):
        self.assertEqual(MULTILINGUAL_MODEL_NAME, "intfloat/multilingual-e5-large")
        self.assertEqual(MULTILINGUAL_VECTOR_DIM, 1024)
        self.assertEqual(EvidenceVectorStore.DEFAULT_MODEL, MULTILINGUAL_MODEL_NAME)


class TestAlmacenDeEvidencia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rir_vect_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.almacen = EvidenceVectorStore(self.tmp, embedder=HashEmbedder(dim=32))

    def test_upsert_idempotente_por_id_global(self):
        self.almacen.upsert([item("1", "export invoices by hand"), item("2", "otra queja")])
        self.almacen.upsert([item("1", "export invoices by hand, updated")])
        self.assertEqual(self.almacen.count(), 2)
        fila = self.almacen.get("hackernews:1")
        self.assertEqual(fila["text"], "export invoices by hand, updated")

    def test_cada_fila_lleva_fuente_e_id_global_y_ningun_autor(self):
        self.almacen.upsert([item("1", "texto", fuente="stackexchange")])
        fila = self.almacen.get("stackexchange:1")
        self.assertEqual((fila["source"], fila["community"], fila["data_source"]),
                         ("stackexchange", "Ask HN", "real"))
        self.assertFalse({"author", "author_hash"} & set(self.almacen.columnas()))

    def test_busca_por_similitud_y_entrega_vectores(self):
        self.almacen.upsert([item("1", "invoice export pain"), item("2", "garden flowers")])
        ids = [f["id"] for f in self.almacen.similar("invoice export pain", limit=1)]
        self.assertEqual(ids, ["hackernews:1"])
        vectores = self.almacen.vectors(["hackernews:1", "hackernews:2", "no:existe"])
        self.assertEqual(set(vectores), {"hackernews:1", "hackernews:2"})
        self.assertEqual(len(vectores["hackernews:1"]), 32)

    def test_sin_items_no_hace_nada(self):
        self.assertEqual(self.almacen.upsert([]), 0)
        self.assertEqual(self.almacen.count(), 0)

    def test_delete_borra_por_id_global(self):
        self.almacen.upsert([item("1", "uno"), item("2", "dos")])
        self.almacen.delete(["hackernews:1", "no:existe"])
        self.assertEqual(self.almacen.count(), 1)
        self.assertIsNone(self.almacen.get("hackernews:1"))
        self.almacen.delete([])

    def test_embed_da_los_vectores_por_id_y_upsert_los_reutiliza(self):
        # e5-large en CPU es lento: lo que calculó la deduplicación no se repite.
        items = [item("1", "invoice export pain"), item("2", "garden flowers")]
        vectores = self.almacen.embed(items)
        self.assertEqual(set(vectores), {"hackernews:1", "hackernews:2"})
        with unittest.mock.patch.object(self.almacen.embedder, "embed_batch",
                                        side_effect=AssertionError("recalculado")):
            self.almacen.upsert(items, vectors=vectores)
        guardado = self.almacen.vectors(["hackernews:1"])["hackernews:1"]
        self.assertTrue(np.allclose(guardado, vectores["hackernews:1"]))

    def test_upsert_calcula_solo_los_que_faltan(self):
        items = [item("1", "invoice export pain"), item("2", "garden flowers")]
        vectores = self.almacen.embed(items[:1])
        with unittest.mock.patch.object(self.almacen.embedder, "embed_batch",
                                        wraps=self.almacen.embedder.embed_batch) as espia:
            self.almacen.upsert(items, vectors=vectores)
        espia.assert_called_once_with(["garden flowers"])
        self.assertEqual(self.almacen.count(), 2)


if __name__ == "__main__":
    unittest.main()
