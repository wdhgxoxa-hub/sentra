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
        self.assertIn("facturas clientes pagan", propuesta.es)
        self.assertGreaterEqual(len(propuesta.es), 3)
        self.assertEqual(propuesta.en, [], "sin Gemini no se traduce")

    def test_solo_los_idiomas_elegidos(self):
        self.assertEqual(proponer_sin_gemini("Facturas que los clientes no pagan", ["en"]),
                         PalabrasPropuestas(es=[], en=[]))


class TestTerminosCortos(unittest.TestCase):
    """Fase 3, escaneo 1 (25-09): Gemini propuso frases de queja de 4-6 palabras
    («pdf to word ruins formatting») y HN, Stack Exchange, GitHub, Discourse y
    Product Hunt dieron 0: exigen todas las palabras, la frase exacta o un nombre
    de tema. Medido el 25-09 con llamadas directas: «pdf to word» da 215 en HN
    (90 días), 681 en GitHub (frase exacta) y 50 en Discourse; la frase larga, 0.
    Una palabra clave es un término de 1 a 3 palabras; las frases de queja las
    añade aparte la biblioteca de frases."""

    def test_gemini_no_cuela_frases_de_mas_de_tres_palabras(self):
        modelo = PalabrasPropuestas(es=["pdf a word", "pdf a word pierde formato"],
                                    en=["pdf to word", "pdf converter", "pdf to word ruins formatting"])
        propuesta = proponer_con_gemini(Generador(modelo), "m", "PDF a Word", ["es", "en"])
        self.assertEqual((propuesta.es, propuesta.en), (["pdf a word"], ["pdf to word", "pdf converter"]))

    def test_se_piden_terminos_cortos_y_no_quejas(self):
        generador = Generador(PalabrasPropuestas(es=["pdf a word"], en=["pdf to word"]))
        proponer_con_gemini(generador, "m", "PDF a Word", ["es", "en"])
        prompt = generador.pedidos[0]["prompt"]
        self.assertIn("1 a 3 palabras", prompt)
        self.assertIn("no frases de queja", prompt)

    def test_sin_gemini_tambien_son_cortas(self):
        propuesta = proponer_sin_gemini("Convertir un PDF a Word sin perder el formato", ["es", "en"])
        self.assertTrue(propuesta.es)
        for palabra in propuesta.es:
            with self.subTest(palabra=palabra):
                self.assertLessEqual(len(palabra.split()), 3)
        self.assertIn("convertir pdf word", propuesta.es)


class TestConGemini(unittest.TestCase):
    def test_limpia_la_propuesta_y_la_pide_como_palabras_clave(self):
        modelo = PalabrasPropuestas(
            es=["facturas impagadas", "Facturas impagadas ", "", "cliente no paga", "x" * 90,
                "cliente que no paga nunca"],
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


class TestTipoDeTemaYSitios(unittest.TestCase):
    """Medida B (Fase 3): en la misma llamada, Gemini dice si el tema es de software
    y elige, del catálogo cerrado, los sitios de Stack Exchange adecuados."""

    def test_trae_el_tipo_y_los_sitios_del_catalogo(self):
        modelo = PalabrasPropuestas(es=["documentos contabilidad"], tipo="otro",
                                    sitios_stackexchange=["money", "sitio-inventado", "freelancing", "money"])
        generador = Generador(modelo)
        propuesta = proponer_con_gemini(generador, "m", "Perseguir documentos del contable", ["es"])
        self.assertEqual(propuesta.tipo, "otro")
        self.assertEqual(propuesta.sitios_stackexchange, ["money", "freelancing"], "solo del catálogo, sin repetir")
        self.assertEqual(len(generador.pedidos), 1, "misma llamada")

    def test_el_prompt_pide_el_tipo_y_nombra_el_catalogo(self):
        generador = Generador(PalabrasPropuestas())
        proponer_con_gemini(generador, "m", "tema", ["es"])
        prompt = generador.pedidos[0]["prompt"]
        for clave in ("software", "money", "freelancing", "stackoverflow"):
            self.assertIn(clave, prompt)

    def test_sin_gemini_no_se_sabe_el_tipo(self):
        propuesta = proponer_sin_gemini("Perseguir documentos del contable", ["es"])
        self.assertIsNone(propuesta.tipo)
        self.assertEqual(propuesta.sitios_stackexchange, [])


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
        sdk = Cliente(respuesta('{"es": ["facturas impagadas"], "en": ["unpaid invoices"], "tipo": "otro",'
                                ' "sitios_stackexchange": ["money"]}', 300, 40, 0))
        cuerpo = self.pedir(self.cliente(self.con_sdk(sdk))).json()
        # Medida B (Fase 3): el tipo de tema y los sitios viajan aparte de las palabras.
        self.assertEqual(cuerpo, {"keywords": {"es": ["facturas impagadas"], "en": ["unpaid invoices"]},
                                  "topicKind": "otro", "stackexchangeSites": ["money"],
                                  "origin": "gemini", "reason": None, "llmCalls": 1})
        self.assertEqual([(i.purpose, i.outcome) for _, i in self.registro.filas], [("palabras_clave", "ok")])

    def test_sin_clave_propone_sin_gemini_y_no_registra_nada(self):
        from core.llm.gemini import GeminiSinConfigurar

        def sin_clave(_ctx):
            raise GeminiSinConfigurar("sin clave")

        cuerpo = self.pedir(self.cliente(sin_clave)).json()
        self.assertEqual((cuerpo["origin"], cuerpo["reason"], cuerpo["llmCalls"]),
                         ("local", "gemini_not_configured", 0))
        self.assertEqual((cuerpo["topicKind"], cuerpo["stackexchangeSites"]), (None, []))
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
