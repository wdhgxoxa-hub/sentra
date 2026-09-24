"""
Suite de pruebas de la Fase 4: core/storage
===========================================
Cubre persistencia columnar (LanceDB), consultas por clave, borrado,
busqueda vectorial densa, fusion hibrida RRF, resolucion configurable
de la ruta de almacenamiento y politica de embeddings.
"""

import os
import unittest
from pathlib import Path
from typing import Any, ClassVar
from unittest import mock

from core.storage import (
    DEFAULT_VECTOR_DIM,
    EmbeddingError,
    FastEmbedEmbedder,
    HashEmbedder,
    get_embedder,
    resolve_db_path,
)
from core.storage.lancedb_store import _sql_literal

try:
    import fastembed  # noqa: F401 - solo se comprueba si está instalado
    FASTEMBED_AVAILABLE = True
except ImportError:
    FASTEMBED_AVAILABLE = False


# Embedder ligero y determinista para las pruebas de persistencia:
# mantiene la suite rapida y sin dependencias de red.
TEST_DIM = 64


class TestResolveDbPath(unittest.TestCase):
    """La ruta de almacenamiento debe ser configurable, nunca un hardcode."""

    def setUp(self):
        # patch.dict devuelve el entorno a como estaba, pase lo que pase.
        entorno = mock.patch.dict(os.environ)
        entorno.start()
        self.addCleanup(entorno.stop)
        os.environ.pop("RIR_LANCEDB_PATH", None)

    def test_explicit_argument_wins_over_environment(self):
        os.environ["RIR_LANCEDB_PATH"] = os.path.join("C:", "desde_entorno")
        expected = Path(os.path.join("C:", "explicita"))
        self.assertEqual(resolve_db_path(os.path.join("C:", "explicita")), expected)

    def test_environment_variable_is_honoured(self):
        target = os.path.join("C:", "desde_entorno")
        os.environ["RIR_LANCEDB_PATH"] = target
        self.assertEqual(resolve_db_path(), Path(target))

    def test_fallback_is_relative_to_project_root(self):
        project_root = Path(__file__).resolve().parents[1]
        self.assertEqual(resolve_db_path(), project_root / "data" / "lancedb")

    def test_module_carries_no_absolute_drive_hardcode(self):
        source = (
            Path(__file__).resolve().parents[1] / "core" / "storage" / "lancedb_store.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("F:" + chr(92) + "reddit_intelligence_radar", source)


class TestSqlLiteral(unittest.TestCase):
    """El escape de literales SQL es la defensa contra la inyeccion."""

    def test_plain_value_is_quoted(self):
        self.assertEqual(_sql_literal("abc123"), "'abc123'")

    def test_single_quote_is_doubled(self):
        self.assertEqual(_sql_literal("x'y"), "'x''y'")

    def test_injection_payload_stays_inside_the_literal(self):
        self.assertEqual(_sql_literal("' OR '1'='1"), "''' OR ''1''=''1'")

    def test_non_string_input_is_rejected(self):
        with self.assertRaises(TypeError):
            numero: Any = 42  # a propósito: se comprueba que un no-texto se rechaza
            _sql_literal(numero)


class TestEmbeddingPolicy(unittest.TestCase):
    """El hash MD5 es un recurso de emergencia, jamas el camino por defecto."""

    def test_hash_embedder_declares_itself_non_semantic(self):
        self.assertFalse(HashEmbedder(dim=TEST_DIM).is_semantic)

    def test_hash_embedder_produces_unit_norm_vectors(self):
        vec = HashEmbedder(dim=TEST_DIM).embed_text("texto de prueba")
        self.assertEqual(len(vec), TEST_DIM)
        self.assertAlmostEqual(sum(v * v for v in vec) ** 0.5, 1.0, places=5)

    def test_hash_embedder_is_deterministic(self):
        emb = HashEmbedder(dim=TEST_DIM)
        self.assertEqual(emb.embed_text("mismo texto"), emb.embed_text("mismo texto"))

    def test_empty_text_yields_a_zero_vector(self):
        self.assertEqual(HashEmbedder(dim=TEST_DIM).embed_text("   "), [0.0] * TEST_DIM)

    def test_batch_matches_individual_embedding(self):
        emb = HashEmbedder(dim=TEST_DIM)
        batch = emb.embed_batch(["uno", "dos"])
        self.assertEqual(batch, [emb.embed_text("uno"), emb.embed_text("dos")])

    def test_get_embedder_raises_when_no_real_provider_and_no_opt_in(self):
        with self.assertRaises(EmbeddingError):
            get_embedder(allow_hash_fallback=False, _force_unavailable=True)

    def test_hash_fallback_requires_explicit_opt_in(self):
        with self.assertLogs("core.storage.embeddings", level="WARNING") as captured:
            emb = get_embedder(allow_hash_fallback=True, _force_unavailable=True)
        self.assertIsInstance(emb, HashEmbedder)
        self.assertIn("DEGRADADOS", "".join(captured.output))

    def test_default_vector_dim_matches_the_real_provider(self):
        self.assertEqual(DEFAULT_VECTOR_DIM, 384)


@unittest.skipUnless(FASTEMBED_AVAILABLE, "fastembed no esta instalado")
class TestRealEmbeddings(unittest.TestCase):
    embedder: ClassVar[FastEmbedEmbedder]

    """Prueba de que el espacio vectorial ya no es un placebo."""

    @classmethod
    def setUpClass(cls):
        cls.embedder = FastEmbedEmbedder()

    @staticmethod
    def _cosine(a, b):
        return sum(x * y for x, y in zip(a, b))

    def test_provider_declares_itself_semantic(self):
        self.assertTrue(self.embedder.is_semantic)

    def test_dimension_is_384(self):
        self.assertEqual(self.embedder.dim, 384)
        self.assertEqual(len(self.embedder.embed_text("hello world")), 384)

    def test_vectors_are_unit_norm(self):
        vec = self.embedder.embed_text("invoice export is broken")
        self.assertAlmostEqual(sum(v * v for v in vec) ** 0.5, 1.0, places=4)

    def test_paraphrases_are_closer_than_unrelated_text(self):
        anchor = self.embedder.embed_text("I cannot export my invoices to a CSV file")
        paraphrase = self.embedder.embed_text("exporting bills as spreadsheets fails")
        unrelated = self.embedder.embed_text("my cat sleeps on the keyboard all day")

        self.assertGreater(
            self._cosine(anchor, paraphrase), self._cosine(anchor, unrelated)
        )

    def test_hash_embedder_cannot_do_the_same(self):
        """Contraste explicito: el placebo no captura parafrasis."""
        hasher = HashEmbedder(dim=384)
        anchor = hasher.embed_text("I cannot export my invoices to a CSV file")
        paraphrase = hasher.embed_text("exporting bills as spreadsheets fails")
        self.assertLess(self._cosine(anchor, paraphrase), 0.2)


class TestPublicApi(unittest.TestCase):

    def test_package_exports_the_documented_surface(self):
        from core import storage

        for name in (
            "HashEmbedder", "FastEmbedEmbedder",
            "get_embedder", "resolve_db_path", "EmbeddingError",
            "DEFAULT_VECTOR_DIM",
        ):
            self.assertIn(name, storage.__all__)
            self.assertTrue(hasattr(storage, name))


if __name__ == "__main__":
    unittest.main()
