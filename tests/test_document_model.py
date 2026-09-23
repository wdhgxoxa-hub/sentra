"""
Un solo modelo para el PRD de la interfaz y el PDF (AUD-022, decisión D-H)
=========================================================================

La interfaz pintaba siete apartados del PRD y el PDF diez secciones, con
otro contenido y otro orden. Ahora `/api/blueprint` entrega las secciones del
mismo `DocumentModel` con el que se genera el PDF: el conjunto y el orden de
secciones son idénticos, y también su texto.
"""

import io
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfReader

from core.documents.model import SECTION_IDS, build_document
from core.documents.pdf_report import build_pdf
from core.ingestion.synthetic import SyntheticFetcher
from core.orchestration import RadarDependencies
from core.orchestration.sidecar_server import create_app
from core.storage import HashEmbedder, HybridSearchEngine, LanceDBStore
from tests._sin_red import prohibir_red_real
from tests.test_pdf_export import cluster

PLAN = "# FASE 1\n\n## Lógica central\n\n- Paso uno"


def texto_pdf(pdf: bytes) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)


class ConSidecar(unittest.TestCase):

    def setUp(self):
        prohibir_red_real(self)
        self.tmp = Path(tempfile.mkdtemp(prefix="rir_documento_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        store = LanceDBStore(db_path=str(self.tmp / "lance"), embedder=HashEmbedder(dim=32))
        deps = RadarDependencies(fetcher=SyntheticFetcher(), store=store,
                                 search_engine=HybridSearchEngine(store=store))
        self.client = TestClient(create_app(insecure_dev=True, deps=deps, persist_default=False,
                                            env_path=str(self.tmp / ".env")))


    def prd(self, idioma="es", architecture=None):
        respuesta = self.client.post("/api/blueprint", json={
            "cluster": cluster(), "language": idioma, "architecture": architecture})
        self.assertEqual(respuesta.status_code, 200, respuesta.text[:200])
        return respuesta.json()


class TestMismoDocumento(ConSidecar):

    def test_la_interfaz_recibe_las_diez_secciones_en_orden(self):
        for idioma in ("es", "en"):
            secciones = self.prd(idioma)["sections"]
            self.assertEqual([s["id"] for s in secciones], list(SECTION_IDS))

    def test_secciones_de_la_interfaz_y_del_pdf_identicas_en_conjunto_y_orden(self):
        for idioma in ("es", "en"):
            titulos = [s["title"] for s in self.prd(idioma)["sections"]]
            cuerpo = texto_pdf(build_pdf(cluster(), idioma, version="0.1.0"))
            cuerpo = cuerpo[cuerpo.find(titulos[0], cuerpo.find(titulos[-1]) + 1):]
            posiciones = [cuerpo.find(t) for t in titulos]
            self.assertNotIn(-1, posiciones, (idioma, posiciones))
            self.assertEqual(posiciones, sorted(posiciones), idioma)

    def test_el_texto_de_cada_bloque_de_la_interfaz_esta_en_el_pdf(self):
        pdf = " ".join(texto_pdf(build_pdf(cluster(), "es", version="0.1.0")).split())
        for seccion in self.prd("es")["sections"]:
            for bloque in seccion["blocks"]:
                if bloque["kind"] in ("paragraph", "note", "subheading"):
                    with self.subTest(seccion=seccion["id"], texto=bloque["text"][:40]):
                        self.assertIn(" ".join(bloque["text"].split())[:60], pdf)

    def test_el_plan_de_la_sesion_llega_a_la_seccion_7_de_la_interfaz(self):
        sin = {s["id"]: s for s in self.prd("es")["sections"]}["architecture"]
        self.assertIn("No generado", sin["blocks"][0]["text"])
        con = {s["id"]: s for s in self.prd("es", PLAN)["sections"]}["architecture"]
        self.assertEqual(con["blocks"][-1], {"kind": "markdown", "text": PLAN, "items": [],
                                             "signature": "", "rows": []})

    def test_copiar_en_markdown_es_el_mismo_documento(self):
        doc = self.prd("es")
        for seccion in doc["sections"]:
            self.assertIn(f"## {seccion['title']}", doc["markdown"])


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
