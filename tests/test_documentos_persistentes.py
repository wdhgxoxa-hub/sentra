"""
Un documento generado con Gemini no se pierde nunca (Fase 1, decisión de Walter)
================================================================================

El 2026-09-25 el dossier de impagos se generó (1 llamada, 5 009 tokens), el
diálogo de guardar se canceló, la app se cerró y el texto se perdió: solo
vivía en la memoria del motor. Ahora el motor lo guarda en disco
(%LOCALAPPDATA%\\SENTRA\\documentos) ANTES de responder, que es antes de que
Rust abra el diálogo, y lo vuelve a exportar desde ahí sin llamar al modelo,
aunque la app se haya cerrado.
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from core.documents.almacen import AlmacenDeDocumentos
from core.llm.control import RegistroEnMemoria
from tests._sin_red import prohibir_red_real
from tests.test_documents_compose import detalle
from tests.test_documents_generate import Doble
from tests.test_llm_provider import Cliente, respuesta

VEREDICTO = "11111111-1111-1111-1111-111111111111"


def dossier_en_json() -> str:
    """Lo que devolvería Gemini: el esquema entero del dossier, válido."""
    from core.documents.generate import _ESQUEMAS

    entero = _ESQUEMAS["dossier"][0]
    instancia = Doble().generate_json("", entero, model="m", max_output_tokens=1, timeout_ms=1, purpose="dossier")
    return instancia.model_dump_json()


class TestAlmacen(unittest.TestCase):
    def test_un_documento_vuelve_igual_de_disco(self):
        from datetime import UTC, datetime

        from core.documents.claims import DossierLLM
        from core.documents.compose import compose_dossier

        contenido = DossierLLM.model_validate_json(dossier_en_json())
        documento = compose_dossier(detalle(), contenido, "es", model="m", generated_at=datetime(2026, 9, 25, tzinfo=UTC))
        carpeta = Path(tempfile.mkdtemp(prefix="almacen_"))
        self.addCleanup(shutil.rmtree, carpeta, True)
        clave = (VEREDICTO, "dossier", "es", "m", False)
        AlmacenDeDocumentos(carpeta).guardar(clave, documento)
        self.assertEqual(AlmacenDeDocumentos(carpeta).leer(clave), documento)
        self.assertIsNone(AlmacenDeDocumentos(carpeta).leer((VEREDICTO, "plan", "es", "m", False)))


class _AppConDisco(unittest.TestCase):
    """Motor con una carpeta de documentos propia y un SDK de Gemini falso."""

    def setUp(self):
        prohibir_red_real(self)
        self.carpeta = Path(tempfile.mkdtemp(prefix="documentos_"))
        self.addCleanup(shutil.rmtree, self.carpeta, True)
        self.registro = RegistroEnMemoria()  # el llm_usage de las dos aperturas
        self.sdk = Cliente(*[respuesta(dossier_en_json(), 1435, 1399, 2175) for _ in range(3)])

    def abrir_la_app(self) -> TestClient:
        """Una apertura nueva: motor nuevo, memoria vacía, mismo disco."""
        from core.llm.gemini import GeminiProvider
        from core.orchestration import sidecar_server
        from core.orchestration.sidecar import documents

        parches = [
            mock.patch.object(sidecar_server, "_registro_de_uso", return_value=self.registro),
            mock.patch.object(documents, "_disponible", return_value=True),
            mock.patch.object(documents, "_cargar", return_value=detalle()),
            mock.patch.object(documents, "_proveedor", side_effect=lambda ctx: (
                GeminiProvider("clave", control=ctx.control(), client_factory=self.sdk), "gemini-pro")),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)
        app = sidecar_server.create_app(insecure_dev=True, persist_default=False,
                                        carpeta_documentos=self.carpeta)
        return TestClient(app)

    def exportar(self, cliente: TestClient):
        return cliente.post("/api/documents/dossier",
                            json={"verdictId": VEREDICTO, "format": "md", "language": "es"})


class TestNoSePierde(_AppConDisco):
    def test_se_genera_se_cancela_se_cierra_y_se_vuelve_a_exportar_sin_llamar(self):
        primera = self.exportar(self.abrir_la_app())
        self.assertEqual((primera.status_code, primera.headers["x-sentra-llm-calls"]), (200, "1"))
        self.assertEqual(len(self.registro.filas), 1)
        self.assertTrue(list(self.carpeta.glob("*.json")), "se guardó en disco antes de responder")

        # El diálogo se cancela y la app se cierra: la memoria del motor se pierde.
        segunda = self.exportar(self.abrir_la_app())
        self.assertEqual((segunda.status_code, segunda.headers["x-sentra-llm-calls"]), (200, "0"))
        self.assertEqual(segunda.text, primera.text)
        self.assertEqual(len(self.registro.filas), 1, "llm_usage no suma filas")
        self.assertEqual(len(self.sdk.llamadas), 1)


class TestEstadoYReutilizacion(_AppConDisco):
    """Fase 2: la ficha del nicho dice si el dossier y el plan ya están
    guardados (se abren sin gastar) sin llamar a nadie, y exportar lo guardado
    no resuelve el modelo: listar modelos puede llamar a Google."""

    def estado(self, cliente: TestClient):
        return cliente.get("/api/documents/status", params={"verdictId": VEREDICTO})

    def test_el_estado_dice_que_esta_guardado_sin_llamar_al_modelo(self):
        cliente = self.abrir_la_app()
        antes = self.estado(cliente)
        self.assertEqual(antes.status_code, 200)
        self.assertEqual(antes.json(), {"verdictId": VEREDICTO,
                                        "dossier": {"es": False, "en": False},
                                        "plan": {"es": False, "en": False}})
        self.exportar(cliente)
        despues = self.estado(self.abrir_la_app()).json()
        self.assertEqual((despues["dossier"], despues["plan"]),
                         ({"es": True, "en": False}, {"es": False, "en": False}))
        self.assertEqual(len(self.sdk.llamadas), 1, "solo la exportación llamó")

    def test_el_estado_de_un_id_que_no_es_uuid_es_un_400(self):
        self.assertEqual(self.abrir_la_app().get("/api/documents/status",
                                                 params={"verdictId": "../x"}).status_code, 400)

    def test_exportar_lo_guardado_no_resuelve_el_modelo(self):
        from core.orchestration.sidecar import documents

        self.exportar(self.abrir_la_app())
        cliente = self.abrir_la_app()
        with mock.patch.object(documents, "_proveedor",
                               side_effect=AssertionError("no debe resolver el modelo")):
            otra = self.exportar(cliente)
        self.assertEqual((otra.status_code, otra.headers["x-sentra-llm-calls"]), (200, "0"))
        self.assertEqual(len(self.registro.filas), 1)


if __name__ == "__main__":
    unittest.main()
