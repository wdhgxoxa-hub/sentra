"""
Modelos de Gemini en el sidecar (F1.2, F1.3, F1.6)
==================================================

La configuración ofrece solo los modelos que la clave puede usar
(`models.list`). Hay dos usos:

- general (traducción, etiquetado): por defecto, el Flash estable 3.x más reciente;
- documentos (plan de arquitectura): por defecto, el Pro 3.x más reciente.

Cada uso admite un modelo guardado. Si el guardado desaparece de la lista,
error tipado `llm_model_unavailable`, nunca un cambio silencioso. Ningún
test sale a la red: el cliente del SDK es un doble con catálogo.
"""

import json
import unittest
from unittest import mock

from tests._gemini_dobles import ClienteConCatalogo
from tests.test_sidecar_config import ConfigTestCase

CLAVE = "AIzaSy-CLAVE-FALSA-PARA-TESTS"


class ConCatalogo(ConfigTestCase):
    def setUp(self):
        super().setUp()
        ClienteConCatalogo.llamadas_a_list = 0
        parche = mock.patch("core.llm.gemini._cliente_real", ClienteConCatalogo)
        parche.start()
        self.addCleanup(parche.stop)

    def guardar(self, **campos):
        return self.client.post("/api/gemini", json={"apiKey": CLAVE, **campos})

    def plan(self, capturado):
        def falso(cluster, **kwargs):
            capturado.update(kwargs)
            yield "ok"

        with mock.patch("core.intelligence.gemini_architect.stream_architecture", falso):
            respuesta = self.client.post("/api/architect/generate", json={"cluster": {"label": "x"}})
        return [json.loads(linea) for linea in respuesta.text.splitlines() if linea]


class TestConfiguracion(ConCatalogo):
    def test_sin_modelos_guardados_ambos_usos_son_automaticos(self):
        gemini = self.client.get("/api/config").json()["gemini"]
        self.assertIsNone(gemini["model"])
        self.assertIsNone(gemini["generalModel"])

    def test_se_guardan_los_dos_modelos(self):
        self.guardar(model="gemini-3.1-pro-preview", generalModel="gemini-3.5-flash")
        gemini = self.client.get("/api/config").json()["gemini"]
        self.assertEqual(gemini["model"], "gemini-3.1-pro-preview")
        self.assertEqual(gemini["generalModel"], "gemini-3.5-flash")


class TestListaDeModelos(ConCatalogo):
    def test_sin_clave_lo_dice_con_codigo(self):
        cuerpo = self.client.get("/api/gemini/models").json()
        self.assertFalse(cuerpo["ok"])
        self.assertEqual(cuerpo["code"], "gemini_not_configured")
        self.assertEqual(cuerpo["models"], [])

    def test_ofrece_solo_los_que_generan_texto_y_los_elegidos_por_defecto(self):
        self.guardar()
        cuerpo = self.client.get("/api/gemini/models").json()
        self.assertTrue(cuerpo["ok"])
        ids = [m["id"] for m in cuerpo["models"]]
        self.assertNotIn("text-embedding-004", ids)
        self.assertIn("gemini-3.6-flash-lite", ids)  # elegible a mano, no por defecto
        self.assertEqual(cuerpo["general"], "gemini-3.6-flash")
        self.assertEqual(cuerpo["documents"], "gemini-3.1-pro-preview")

    def test_la_lista_se_guarda_un_rato_y_no_gasta_una_llamada_por_peticion(self):
        self.guardar()
        self.client.get("/api/gemini/models")
        self.client.get("/api/gemini/models")
        self.plan({})
        self.assertEqual(ClienteConCatalogo.llamadas_a_list, 1)

    def test_guardar_otra_clave_vacia_la_lista(self):
        self.guardar()
        self.client.get("/api/gemini/models")
        self.guardar()
        self.client.get("/api/gemini/models")
        self.assertEqual(ClienteConCatalogo.llamadas_a_list, 2)


class TestProbarClave(ConCatalogo):
    def test_probar_lista_modelos_sin_generar_texto(self):
        self.guardar()
        cuerpo = self.client.post("/api/gemini/test").json()
        self.assertTrue(cuerpo["ok"])
        self.assertIn("gemini-3.6-flash", cuerpo["detail"])
        self.assertEqual(ClienteConCatalogo.llamadas_a_list, 1)

    def test_un_fallo_de_red_no_se_presenta_como_clave_mala(self):
        import httpx

        class SinRed:
            def __init__(self, _clave):
                self.models = self

            def list(self):
                raise httpx.ConnectError("sin red")

        self.guardar()
        with mock.patch("core.llm.gemini._cliente_real", SinRed):
            cuerpo = self.client.post("/api/gemini/test").json()
        self.assertFalse(cuerpo["ok"])
        self.assertNotIn("La clave no funciona", cuerpo["detail"])
        self.assertIn("contactar", cuerpo["detail"])


class TestResolucionAlUsar(ConCatalogo):
    def test_el_plan_usa_por_defecto_el_pro_mas_reciente(self):
        self.guardar()
        vistos = {}
        self.plan(vistos)
        self.assertEqual(vistos["model"], "gemini-3.1-pro-preview")
        self.assertEqual(vistos["api_key"], CLAVE)

    def test_el_plan_respeta_el_modelo_guardado(self):
        self.guardar(model="gemini-2.5-flash")
        vistos = {}
        self.plan(vistos)
        self.assertEqual(vistos["model"], "gemini-2.5-flash")

    def test_si_el_modelo_guardado_desaparece_el_plan_termina_en_error_tipado(self):
        self.guardar(model="gemini-2.0-flash")
        vistos = {}
        eventos = self.plan(vistos)
        self.assertEqual(vistos, {}, "no debe llamar al modelo")
        self.assertEqual(eventos[-1]["type"], "error")
        self.assertEqual(eventos[-1]["code"], "llm_model_unavailable")

    def test_la_traduccion_usa_el_modelo_general(self):
        self.guardar()
        vistos = {}

        def falso(textos, target, **kwargs):
            vistos.update(kwargs)
            return []

        with mock.patch("core.intelligence.translator.translate", falso):
            self.client.post("/api/translate", json={"texts": ["hola"], "target": "en"})
        self.assertEqual(vistos["model"], "gemini-3.6-flash")


if __name__ == "__main__":
    unittest.main()
