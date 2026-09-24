"""
Modelos de Gemini en el sidecar (F1.2, F1.3, F1.6)
==================================================

La configuración ofrece solo los modelos que la clave puede usar
(`models.list`). Hay dos usos:

- general (etiquetado del juez): por defecto, el Flash estable 3.x más reciente;
- documentos (dossier y plan de la Fase E): por defecto, el Pro 3.x más reciente.

Cada uso admite un modelo guardado. Si el guardado desaparece de la lista,
error tipado `llm_model_unavailable`, nunca un cambio silencioso. Ningún
test sale a la red: el cliente del SDK es un doble con catálogo.
"""

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

    def resolver(self, uso):
        """Lo que resuelve el sidecar al usar Gemini (antes se miraba a través
        del plan de arquitectura y la traducción, retirados en C2)."""
        from core.orchestration.sidecar.context import SidecarContext

        ctx = SidecarContext(persist_default=False, postgres_dsn=None,
                             env_path=str(self.env_path), started_at=0.0)
        return ctx.resolver_modelo(uso)


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


class TestGuardarModelos(ConCatalogo):
    def test_sin_clave_nueva_se_cambian_los_modelos_y_se_conserva_la_guardada(self):
        """Elegir modelo no obliga a volver a teclear la clave."""
        self.guardar()
        respuesta = self.client.post(
            "/api/gemini", json={"apiKey": "", "model": "gemini-2.5-flash",
                                 "generalModel": "gemini-3.5-flash"}
        )
        self.assertEqual(respuesta.status_code, 200)
        gemini = self.client.get("/api/config").json()["gemini"]
        self.assertTrue(gemini["configured"])
        self.assertEqual(gemini["model"], "gemini-2.5-flash")
        self.assertEqual(gemini["generalModel"], "gemini-3.5-flash")
        self.assertIn(CLAVE, self.env_path.read_text(encoding="utf-8"))

    def test_sin_clave_nueva_ni_guardada_se_rechaza(self):
        respuesta = self.client.post("/api/gemini", json={"apiKey": "", "model": ""})
        self.assertEqual(respuesta.status_code, 400)


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
        # D1: la interfaz no tiene que adivinarlo por el texto.
        self.assertEqual(cuerpo["code"], "gemini_unavailable")

    def probar_con(self, error):
        class Falla:
            def __init__(self, _clave):
                self.models = self

            def list(self):
                raise error

        self.guardar()
        with mock.patch("core.llm.gemini._cliente_real", Falla):
            return self.client.post("/api/gemini/test").json()

    def test_una_clave_rechazada_se_dice_con_su_codigo(self):
        from google.genai import errors

        rechazo = errors.ClientError(400, {"error": {
            "code": 400, "message": "API key not valid. Please pass a valid API key.",
            "status": "INVALID_ARGUMENT",
            "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo",
                         "reason": "API_KEY_INVALID"}]}})
        cuerpo = self.probar_con(rechazo)
        self.assertEqual((cuerpo["ok"], cuerpo["code"]), (False, "gemini_key_rejected"))
        self.assertIn("La clave no funciona", cuerpo["detail"])

    def test_sin_permiso_tambien_es_clave_rechazada(self):
        from google.genai import errors

        cuerpo = self.probar_con(errors.ClientError(403, {"error": {
            "code": 403, "message": "Permission denied", "status": "PERMISSION_DENIED"}}))
        self.assertEqual(cuerpo["code"], "gemini_key_rejected")

    def test_otro_fallo_de_la_api_no_se_da_por_clave_mala(self):
        from google.genai import errors

        cuerpo = self.probar_con(errors.ClientError(400, {"error": {
            "code": 400, "message": "Bad request", "status": "INVALID_ARGUMENT"}}))
        self.assertEqual(cuerpo["code"], "gemini_error")
        self.assertNotIn("La clave no funciona", cuerpo["detail"])

    def test_la_cuota_agotada_no_es_ni_red_ni_clave_mala(self):
        from google.genai import errors

        cuerpo = self.probar_con(errors.ClientError(429, {"error": {
            "code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}}))
        self.assertEqual(cuerpo["code"], "gemini_rate_limited")
        self.assertNotIn("La clave no funciona", cuerpo["detail"])

    def test_con_la_clave_buena_no_hay_codigo(self):
        self.guardar()
        self.assertIsNone(self.client.post("/api/gemini/test").json()["code"])


class TestResolucionAlUsar(ConCatalogo):
    def test_documentos_usa_por_defecto_el_pro_mas_reciente(self):
        self.guardar()
        self.assertEqual(self.resolver("documentos"), (CLAVE, "gemini-3.1-pro-preview"))

    def test_documentos_respeta_el_modelo_guardado(self):
        self.guardar(model="gemini-2.5-flash")
        self.assertEqual(self.resolver("documentos")[1], "gemini-2.5-flash")

    def test_si_el_modelo_guardado_desaparece_es_un_error_tipado(self):
        from core.llm.base import LLMModelUnavailable

        self.guardar(model="gemini-2.0-flash")
        with self.assertRaises(LLMModelUnavailable) as caso:
            self.resolver("documentos")
        self.assertEqual(caso.exception.code, "llm_model_unavailable")

    def test_el_uso_general_va_al_flash(self):
        self.guardar()
        self.assertEqual(self.resolver("defecto")[1], "gemini-3.6-flash")

    def test_sin_clave_no_hay_modelo(self):
        from core.llm.gemini import GeminiSinConfigurar

        with self.assertRaises(GeminiSinConfigurar):
            self.resolver("defecto")


if __name__ == "__main__":
    unittest.main()
