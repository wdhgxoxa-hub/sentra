"""
/api/documents/{kind}: dossier y plan en PDF o Markdown (E6)
===========================================================

El sidecar carga el veredicto, pide el texto al modelo de documentos (una
sola vez por veredicto, documento, idioma, modelo y forzado: lo generado se
guarda en memoria), lo compone y lo pinta en el formato pedido. El plan de un
nicho que no es CONSTRUIR se rechaza con código antes de gastar una llamada,
salvo que se fuerce. La base y el modelo son dobles: ningún test sale a la
red ni toca PostgreSQL.
"""

import unittest
from unittest import mock

from core.llm.gemini import GeminiSinConfigurar
from tests.test_documents_compose import detalle
from tests.test_documents_generate import Doble
from tests.test_sidecar_config import ConfigTestCase


class ConDocumentos(ConfigTestCase):
    def setUp(self):
        super().setUp()
        from core.orchestration.sidecar import documents

        self.doble = Doble()
        self.veredictos = {"11111111-1111-1111-1111-111111111111": detalle(),
                           "33333333-3333-3333-3333-333333333333": detalle("INVESTIGAR MÁS")}
        for nombre, valor in (
            ("_disponible", mock.Mock(return_value=True)),
            ("_cargar", mock.Mock(side_effect=lambda _ctx, vid: self.veredictos.get(vid))),
            ("_proveedor", mock.Mock(return_value=(self.doble, "gemini-pro"))),
        ):
            parche = mock.patch.object(documents, nombre, valor)
            parche.start()
            self.addCleanup(parche.stop)

    def pedir(self, kind, verdict_id="11111111-1111-1111-1111-111111111111", **cuerpo):
        return self.client.post(f"/api/documents/{kind}",
                                json={"verdictId": verdict_id, "format": "pdf", "language": "es",
                                      **cuerpo})


class TestDocumentos(ConDocumentos):
    def test_el_dossier_en_pdf_y_despues_en_markdown_con_una_sola_llamada(self):
        pdf = self.pedir("dossier")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertEqual(pdf.headers["content-type"], "application/pdf")
        self.assertEqual(pdf.headers["x-sentra-llm-calls"], "1")
        self.assertIn("Dossier", pdf.headers["x-sentra-file-name"])

        md = self.pedir("dossier", format="md")
        self.assertEqual(md.status_code, 200)
        self.assertTrue(md.headers["content-type"].startswith("text/markdown"))
        self.assertIn("## 1. Resumen del veredicto", md.text)
        self.assertEqual(md.headers["x-sentra-llm-calls"], "0", "lo generado se reutiliza")
        self.assertEqual(len(self.doble.llamadas), 1)

    def test_el_plan_de_un_nicho_no_construir_se_rechaza_sin_gastar_una_llamada(self):
        respuesta = self.pedir("plan", "33333333-3333-3333-3333-333333333333")
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.json()["detail"]["code"], "plan_not_recommended")
        self.assertEqual(self.doble.llamadas, [])

    def test_forzado_lleva_la_franja(self):
        respuesta = self.pedir("plan", "33333333-3333-3333-3333-333333333333", format="md", force=True)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.text.startswith("> **El juez no recomienda construir este nicho"))

    def test_un_veredicto_que_no_existe_es_404_con_codigo(self):
        respuesta = self.pedir("dossier", "00000000-0000-0000-0000-00000000dead")
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(respuesta.json()["detail"]["code"], "verdict_not_found")

    def test_tipo_formato_o_idioma_desconocidos_se_rechazan(self):
        self.assertEqual(self.pedir("informe").status_code, 422)
        self.assertEqual(self.pedir("dossier", format="docx").status_code, 422)
        self.assertEqual(self.pedir("dossier", language="fr").status_code, 422)

    def test_sin_clave_de_gemini_se_dice_con_su_codigo(self):
        from core.orchestration.sidecar import documents

        with mock.patch.object(documents, "_proveedor", side_effect=GeminiSinConfigurar("sin clave")):
            respuesta = self.pedir("dossier")
        self.assertEqual(respuesta.status_code, 412)
        self.assertEqual(respuesta.json()["detail"]["code"], "gemini_not_configured")


class TestSinBase(ConfigTestCase):
    def test_sin_persistencia_no_hay_documentos(self):
        respuesta = self.client.post("/api/documents/dossier", json={
            "verdictId": "11111111-1111-1111-1111-111111111111", "format": "pdf", "language": "es"})
        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(respuesta.json()["detail"]["code"], "documents_unavailable")


if __name__ == "__main__":
    unittest.main()
