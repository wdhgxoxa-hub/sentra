"""Tests del motor de arquitectura (Gemini).

Ninguno sale a la red: el cliente se inyecta. Lo que se comprueba es lo que
depende de nosotros —qué se le pide al modelo, con qué modelo, y que la clave
no se escape a ningún sitio—, no lo que el modelo responda.
"""

import unittest

from core.intelligence.gemini_architect import (
    MODELO_POR_DEFECTO,
    GeminiSinConfigurar,
    build_prompt,
    probe_api_key,
    stream_architecture,
)

CLAVE = "AIzaSy-CLAVE-DE-PRUEBA-NO-REAL"

CLUSTER = {
    "clusterKey": "complaint:invoice|manual",
    "label": "invoice + manual",
    "intentType": "complaint",
    "keywords": ["invoice", "manual"],
    "subreddits": ["SaaS", "accounting", "bookkeeping"],
    "mentionCount": 5,
    "communityCount": 3,
    "jobStatement": "Exportar facturas a mano se rompe cada mes",
    "currentSolutions": [],
    "urgencyTier": "HIGH",
    "breakdown": {
        "spreadFactor": 1.0,
        "frequencyFactor": 0.2,
        "severityFactor": 1.0,
        "recencyFactor": 1.0,
        "paidSignalFactor": 1.0,
        "rawScore": 74.0,
        "finalScore": 74.0,
    },
    "evidence": [
        {
            "quote": "I would pay for a tool that fixes this",
            "subreddit": "SaaS",
            "author": "ana",
            "url": "u1",
        },
        {
            "quote": "Reconciling by hand eats a whole day",
            "subreddit": "accounting",
            "author": "luis",
            "url": "u2",
        },
    ],
}


class ClienteFalso:
    """Doble del cliente de Gemini, con la misma forma que usa el módulo."""

    def __init__(self, trozos=("uno ", "dos"), error=None):
        self.trozos = trozos
        self.error = error
        self.llamadas = []
        self.models = self._Models(self)

    class _Models:
        def __init__(self, padre):
            self.padre = padre

        def generate_content_stream(self, *, model, contents, config=None):
            self.padre.llamadas.append(
                {"model": model, "contents": contents, "config": config}
            )
            if self.padre.error:
                raise self.padre.error
            for texto in self.padre.trozos:
                yield type("Chunk", (), {"text": texto})()


class TestPrompt(unittest.TestCase):
    def test_la_peticion_lleva_la_evidencia_real(self):
        _, peticion = build_prompt(CLUSTER)
        self.assertIn("invoice + manual", peticion)
        self.assertIn("r/accounting", peticion)
        self.assertIn("5", peticion)
        self.assertIn("I would pay for a tool that fixes this", peticion)

    def test_el_sistema_pide_las_dos_fases(self):
        sistema, _ = build_prompt(CLUSTER)
        for exigido in ("FASE 1", "FASE 2", "MVP", "24"):
            self.assertIn(exigido, sistema)

    def test_el_sistema_pide_codigo_y_esquema(self):
        sistema, _ = build_prompt(CLUSTER)
        texto = sistema.lower()
        for exigido in ("sql", "endpoint", "carpeta", "código"):
            self.assertIn(exigido, texto)

    def test_el_prompt_en_ingles_no_deja_espanol(self):
        sistema, peticion = build_prompt(CLUSTER, language="en")
        for palabra in ("Debes", "comunidades", "señal", "construir"):
            self.assertNotIn(palabra, sistema)
            self.assertNotIn(palabra, peticion)

    def test_la_senal_de_pago_llega_al_prompt(self):
        _, alto = build_prompt(CLUSTER)
        sin_pago = dict(CLUSTER, breakdown=dict(CLUSTER["breakdown"], paidSignalFactor=0.0))
        _, bajo = build_prompt(sin_pago)
        self.assertNotEqual(alto, bajo)


class TestStreaming(unittest.TestCase):
    def test_sin_clave_avisa_en_lugar_de_llamar(self):
        with self.assertRaises(GeminiSinConfigurar):
            list(stream_architecture(CLUSTER, api_key="", client_factory=lambda _k: None))

    def test_devuelve_los_trozos_en_orden(self):
        cliente = ClienteFalso(trozos=("# Fase 1", "\ncontenido"))
        trozos = list(
            stream_architecture(CLUSTER, api_key=CLAVE, client_factory=lambda _k: cliente)
        )
        self.assertEqual(trozos, ["# Fase 1", "\ncontenido"])

    def test_usa_el_modelo_pedido_y_por_defecto_el_pro(self):
        cliente = ClienteFalso()
        list(stream_architecture(CLUSTER, api_key=CLAVE, client_factory=lambda _k: cliente))
        self.assertEqual(cliente.llamadas[0]["model"], MODELO_POR_DEFECTO)
        self.assertEqual(MODELO_POR_DEFECTO, "gemini-2.5-pro")

        otro = ClienteFalso()
        list(
            stream_architecture(
                CLUSTER, api_key=CLAVE, model="gemini-2.5-flash",
                client_factory=lambda _k: otro,
            )
        )
        self.assertEqual(otro.llamadas[0]["model"], "gemini-2.5-flash")

    def test_manda_la_instruccion_de_sistema(self):
        cliente = ClienteFalso()
        list(stream_architecture(CLUSTER, api_key=CLAVE, client_factory=lambda _k: cliente))
        config = cliente.llamadas[0]["config"]
        self.assertIn("FASE 1", config.system_instruction)

    def test_la_clave_no_viaja_dentro_del_prompt(self):
        cliente = ClienteFalso()
        list(stream_architecture(CLUSTER, api_key=CLAVE, client_factory=lambda _k: cliente))
        llamada = cliente.llamadas[0]
        self.assertNotIn(CLAVE, str(llamada["contents"]))
        self.assertNotIn(CLAVE, str(llamada["config"].system_instruction))

    def test_ignora_los_trozos_vacios(self):
        cliente = ClienteFalso(trozos=("a", "", None, "b"))
        trozos = list(
            stream_architecture(CLUSTER, api_key=CLAVE, client_factory=lambda _k: cliente)
        )
        self.assertEqual(trozos, ["a", "b"])


class TestProbe(unittest.TestCase):
    def test_sin_clave_responde_que_no_sin_lanzar(self):
        ok, detalle = probe_api_key("", client_factory=lambda _k: None)
        self.assertFalse(ok)
        self.assertTrue(detalle.strip())

    def test_con_clave_valida_responde_que_si(self):
        ok, detalle = probe_api_key(CLAVE, client_factory=lambda _k: ClienteFalso())
        self.assertTrue(ok)
        self.assertIn(MODELO_POR_DEFECTO, detalle)

    def test_un_fallo_del_servicio_se_cuenta_sin_filtrar_la_clave(self):
        cliente = ClienteFalso(error=RuntimeError(f"401 clave {CLAVE} invalida"))
        ok, detalle = probe_api_key(CLAVE, client_factory=lambda _k: cliente)
        self.assertFalse(ok)
        self.assertNotIn(CLAVE, detalle)


if __name__ == "__main__":
    unittest.main()
