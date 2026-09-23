"""
Deduplicación entre fuentes (F2.6)
==================================

El mismo texto publicado en varias plataformas (crossposting) no es
corroboración: se conserva un ítem, el más antiguo, y se anotan los demás
con el método y la similitud. Dos quejas distintas sobre el mismo problema
SÍ son corroboración y no se funden.
"""

import unittest
from datetime import UTC, datetime, timedelta

import numpy as np

from core.evidence.model import EvidenceItem
from core.sources.dedup import (
    CROSSPOST_MIN_SIMILARITY,
    MIN_CHARS_FOR_SEMANTIC_DEDUP,
    deduplicate,
)

BASE = datetime(2026, 9, 1, tzinfo=UTC)
LARGO = ("Every month I export all our invoices by hand into a spreadsheet because the "
         "accounting tool has no bulk export, and it takes me a whole afternoon.")


def item(nativo, texto, fuente="hackernews", horas=0):
    return EvidenceItem(
        id=f"{fuente}:{nativo}", source=fuente, community="c", kind="post", text=texto,
        url=f"https://example.com/{nativo}", author_hash=None,
        created_at=BASE + timedelta(hours=horas), fetched_at=BASE, data_source="real",
    )


def vector(angulo):
    """Vectores unitarios 2D: el coseno entre dos es cos(diferencia de ángulos)."""
    return [float(np.cos(angulo)), float(np.sin(angulo))]


class TestUmbral(unittest.TestCase):
    def test_el_umbral_tiene_nombre_y_es_exigente(self):
        self.assertEqual(CROSSPOST_MIN_SIMILARITY, 0.95)
        self.assertEqual(MIN_CHARS_FOR_SEMANTIC_DEDUP, 80)


class TestDeduplicar(unittest.TestCase):
    def test_el_mismo_texto_en_dos_plataformas_es_un_solo_item(self):
        original = item("1", LARGO, "hackernews", horas=0)
        copia = item("9", LARGO.upper().replace(" ", "  "), "stackexchange", horas=5)
        resultado = deduplicate([copia, original], vectors={})
        self.assertEqual([i.id for i in resultado.canonical], ["hackernews:1"])
        [dup] = resultado.duplicates
        self.assertEqual((dup.duplicate_id, dup.canonical_id, dup.method, dup.similarity),
                         ("stackexchange:9", "hackernews:1", "fingerprint", None))

    def test_una_copia_retocada_se_detecta_por_embeddings(self):
        a = item("1", LARGO, "hackernews", horas=0)
        b = item("2", LARGO + " (crossposted from HN)", "discourse", horas=2)
        resultado = deduplicate([a, b], vectors={a.id: vector(0.0), b.id: vector(0.1)})
        self.assertEqual([i.id for i in resultado.canonical], ["hackernews:1"])
        [dup] = resultado.duplicates
        self.assertEqual(dup.method, "embedding")
        self.assertAlmostEqual(dup.similarity, float(np.cos(0.1)), places=4)

    def test_dos_quejas_distintas_del_mismo_problema_no_se_funden(self):
        a = item("1", LARGO, horas=0)
        b = item("2", "Our team wastes hours reconciling invoices manually every single month, "
                      "there must be a better way to do this.", horas=1)
        resultado = deduplicate([a, b], vectors={a.id: vector(0.0), b.id: vector(0.45)})
        self.assertEqual(len(resultado.canonical), 2)
        self.assertEqual(resultado.duplicates, [])

    def test_los_textos_cortos_no_se_funden_por_parecido(self):
        a = item("1", "same here, so annoying", horas=0)
        b = item("2", "same here! so annoying", horas=1)
        resultado = deduplicate([a, b], vectors={a.id: vector(0.0), b.id: vector(0.0)})
        self.assertEqual(len(resultado.canonical), 2)

    def test_sin_vector_solo_cuenta_la_huella(self):
        a = item("1", LARGO, horas=0)
        b = item("2", LARGO + " edit", horas=1)
        resultado = deduplicate([a, b], vectors={})
        self.assertEqual(len(resultado.canonical), 2)

    def test_no_encadena_parecidos(self):
        # a≈b y b≈c, pero a y c no se parecen: c no se funde con a por transitividad.
        a, b, c = (item(str(n), LARGO + f" #{n}", horas=n) for n in range(3))
        vectores = {a.id: vector(0.0), b.id: vector(0.25), c.id: vector(0.5)}
        resultado = deduplicate([a, b, c], vectors=vectores)
        self.assertEqual([i.id for i in resultado.canonical], [a.id, c.id])

    def test_sin_items(self):
        resultado = deduplicate([], vectors={})
        self.assertEqual((resultado.canonical, resultado.duplicates), ([], []))


if __name__ == "__main__":
    unittest.main()
