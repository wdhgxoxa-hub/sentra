"""
Un solo modelo para el PRD de la interfaz y el PDF (AUD-022, decisión D-H)
=========================================================================

La interfaz pintaba siete apartados del PRD y el PDF diez secciones, con
otro contenido y otro orden. Ahora `/api/blueprint` entrega las secciones del
mismo `DocumentModel` con el que se genera el PDF: el conjunto y el orden de
secciones son idénticos, y también su texto.
"""

import io
import unittest

from pypdf import PdfReader

from core.documents.model import build_document
from tests.test_pdf_export import cluster

PLAN = "# FASE 1\n\n## Lógica central\n\n- Paso uno"


def texto_pdf(pdf: bytes) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)


class TestAutorAnonimo(unittest.TestCase):
    """R9: el autor se guarda como hash, que sirve para contar autores, no para mostrarlo."""

    def test_las_citas_del_documento_no_muestran_al_autor(self):
        huella = "9f" * 32
        cita = {"quote": "algo roto", "subreddit": "SaaS", "author": huella,
                "url": "https://example.com/c/1", "created_utc": 1758000000.0}
        doc = build_document(cluster(evidence=[cita]), "es")
        firmas = [b.signature for s in doc.sections for b in s.blocks if b.kind == "quote"]
        self.assertTrue(firmas)
        for firma in firmas:
            self.assertNotIn(huella, firma)
            self.assertIn("r/SaaS", firma)
            self.assertIn("https://example.com/c/1", firma)


class TestModelo(unittest.TestCase):

    def test_cada_bloque_tiene_todas_las_claves(self):
        modelo = build_document(cluster(), "es", architecture=PLAN)
        for seccion in modelo.sections:
            for bloque in seccion.blocks:
                self.assertEqual(set(bloque.to_dict()),
                                 {"kind", "text", "items", "signature", "rows"})

    def test_siempre_son_diez_secciones_aunque_falten_datos(self):
        modelo = build_document({"label": "x"}, "en")
        self.assertEqual(len(modelo.sections), 10)
        self.assertEqual(modelo.sections[-1].id, "metadata")


if __name__ == "__main__":
    unittest.main()
