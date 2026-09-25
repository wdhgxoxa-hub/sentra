"""
Palabras clave propuestas para un escaneo (Fase 2, D1)
======================================================

Decisión de Walter: Gemini propone las palabras clave en español e inglés
(una llamada, que cuenta para los topes: propósito «palabras_clave») y, si no
hay clave, no queda presupuesto o Gemini falla, se proponen unas básicas sin
Gemini, que la pantalla marca como tales. El respaldo no traduce: propone en
el idioma en que está escrito el tema, y el aviso de cobertura pide el otro.
"""

import unittest
from unittest import mock

from fastapi.testclient import TestClient

from core.llm.base import LLMBudgetExhausted
from core.llm.control import RegistroEnMemoria, Topes
from core.sources.palabras_clave import (
    PalabrasPropuestas,
    idioma_del_tema,
    proponer_con_gemini,
    proponer_sin_gemini,
)
from tests._sin_red import prohibir_red_real
from tests.test_llm_provider import Cliente, respuesta


class Generador:
    """Doble de JsonGenerator: devuelve lo que diría el modelo y guarda cómo se le pidió."""

    def __init__(self, propuesta: PalabrasPropuestas):
        self.propuesta = propuesta
        self.pedidos: list[dict] = []

    def generate_json(self, prompt, schema, **kwargs):
        self.pedidos.append({"prompt": prompt, **kwargs})
        return schema.model_validate(self.propuesta.model_dump())


class TestIdiomaDelTema(unittest.TestCase):
    def test_reconoce_espanol_e_ingles_por_sus_palabras_comunes(self):
        self.assertEqual(idioma_del_tema("Facturas que los clientes no pagan"), "es")
        self.assertEqual(idioma_del_tema("clients who pay late for the invoices"), "en")
        self.assertEqual(idioma_del_tema("gestión de turnos"), "es", "los acentos también cuentan")


class TestSinGemini(unittest.TestCase):
    def test_propone_en_el_idioma_del_tema_y_no_inventa_el_otro(self):
        propuesta = proponer_sin_gemini("Facturas que los clientes no pagan", ["es", "en"])
        self.assertIn("facturas que los clientes no pagan", propuesta.es)
        self.assertGreaterEqual(len(propuesta.es), 3)
        self.assertEqual(propuesta.en, [], "sin Gemini no se traduce")

    def test_solo_los_idiomas_elegidos(self):
        self.assertEqual(proponer_sin_gemini("Facturas que los clientes no pagan", ["en"]),
                         PalabrasPropuestas(es=[], en=[]))


class TestConGemini(unittest.TestCase):
    def test_limpia_la_propuesta_y_la_pide_como_palabras_clave(self):
        modelo = PalabrasPropuestas(
            es=["facturas impagadas", "Facturas impagadas ", "", "cliente no paga", "x" * 90],
            en=["unpaid invoices", "chasing payments"])
        generador = Generador(modelo)
        propuesta = proponer_con_gemini(generador, "m", "Facturas que los clientes no pagan", ["es", "en"])
        self.assertEqual(propuesta.es, ["facturas impagadas", "cliente no paga"])
        self.assertEqual(propuesta.en, ["unpaid invoices", "chasing payments"])
        self.assertEqual(generador.pedidos[0]["purpose"], "palabras_clave")
        self.assertIn("Facturas que los clientes no pagan", generador.pedidos[0]["prompt"])

    def test_como_mucho_ocho_por_idioma_y_solo_los_elegidos(self):
        modelo = PalabrasPropuestas(es=[f"frase {n}" for n in range(12)], en=["unpaid invoices"])
        propuesta = proponer_con_gemini(Generador(modelo), "m", "tema", ["es"])
        self.assertEqual((len(propuesta.es), propuesta.en), (8, []))


class TestRutaDelMotor(unittest.TestCase):
    """POST /api/scan/keywords: con Gemini, una fila en llm_usage; sin clave, sin
    presupuesto o con error, el respaldo, sin red y sin gastar."""

    def setUp(self):
        prohibir_red_real(self)
        self.registro = RegistroEnMemoria()

    def cliente(self, proveedor=None, registro=None):
        from core.orchestration import sidecar_server
        from core.orchestration.sidecar import palabras

        parches = [mock.patch.object(sidecar_server, "_registro_de_uso",
                                     return_value=registro or self.registro)]
        if proveedor is not None:
            parches.append(mock.patch.object(palabras, "_proveedor", side_effect=proveedor))
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)
        return TestClient(sidecar_server.create_app(insecure_dev=True, persist_default=False))

    def pedir(self, cliente, idiomas=("es", "en")):
        return cliente.post("/api/scan/keywords",
                            json={"topic": "Facturas que los clientes no pagan", "languages": list(idiomas)})

    def con_sdk(self, sdk):
        from core.llm.gemini import GeminiProvider

        return lambda ctx: (GeminiProvider("clave", control=ctx.control(), client_factory=sdk), "flash")

    def test_con_gemini_propone_en_los_dos_idiomas_y_registra_una_llamada(self):
        sdk = Cliente(respuesta('{"es": ["facturas impagadas"], "en": ["unpaid invoices"]}', 300, 40, 0))
        cuerpo = self.pedir(self.cliente(self.con_sdk(sdk))).json()
        self.assertEqual(cuerpo, {"keywords": {"es": ["facturas impagadas"], "en": ["unpaid invoices"]},
                                  "origin": "gemini", "reason": None, "llmCalls": 1})
        self.assertEqual([(i.purpose, i.outcome) for _, i in self.registro.filas], [("palabras_clave", "ok")])

    def test_sin_clave_propone_sin_gemini_y_no_registra_nada(self):
        from core.llm.gemini import GeminiSinConfigurar

        def sin_clave(_ctx):
            raise GeminiSinConfigurar("sin clave")

        cuerpo = self.pedir(self.cliente(sin_clave)).json()
        self.assertEqual((cuerpo["origin"], cuerpo["reason"], cuerpo["llmCalls"]),
                         ("local", "gemini_not_configured", 0))
        self.assertTrue(cuerpo["keywords"]["es"])
        self.assertEqual(self.registro.filas, [])

    def test_sin_presupuesto_hoy_propone_sin_gemini_y_dice_que_tope(self):
        agotado = RegistroEnMemoria(topes=Topes(20, 500_000, 0, 0))
        sdk = Cliente(respuesta('{"es": [], "en": []}'))
        cuerpo = self.pedir(self.cliente(self.con_sdk(sdk), registro=agotado)).json()
        self.assertEqual((cuerpo["origin"], cuerpo["llmCalls"]), ("local", 0))
        self.assertTrue(cuerpo["reason"].startswith("tope_diario"))
        self.assertEqual(sdk.llamadas, [], "la llamada no salió")
        self.assertEqual([i.outcome for _, i in agotado.filas], ["cortada"])

    def test_si_gemini_falla_propone_sin_gemini(self):
        class Roto:
            def generate_json(self, *_a, **_k):
                raise LLMBudgetExhausted("cortada", motivo="tope_diario_llamadas")

        cuerpo = self.pedir(self.cliente(lambda _ctx: (Roto(), "flash"))).json()
        self.assertEqual((cuerpo["origin"], cuerpo["reason"]), ("local", "tope_diario_llamadas"))

    def test_un_tema_vacio_o_sin_idiomas_es_un_422(self):
        cliente = self.cliente(lambda _ctx: self.fail("no debe llegar al modelo"))
        self.assertEqual(cliente.post("/api/scan/keywords", json={"topic": " ", "languages": ["es"]}).status_code,
                         422)
        self.assertEqual(self.pedir(cliente, idiomas=()).status_code, 422)


if __name__ == "__main__":
    unittest.main()
