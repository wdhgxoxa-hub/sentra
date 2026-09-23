"""Tests del traductor de citas.

Ninguno sale a la red. Lo que se comprueba es el contrato: que haya siempre
una respuesta, que se sepa de qué motor viene y que una traducción aproximada
venga marcada como tal.
"""

import unittest

from core.intelligence.translator import (
    Translation,
    clear_cache,
    translate,
)

CLAVE = "AIzaSy-CLAVE-DE-PRUEBA-NO-REAL"
MODELO = "gemini-3.6-flash"


class ClienteFalso:
    """Doble del cliente de Gemini para traducción (sin streaming)."""

    def __init__(self, respuesta='["hola", "adios"]', error=None):
        self.respuesta = respuesta
        self.error = error
        self.llamadas = []
        self.models = self._Models(self)

    class _Models:
        def __init__(self, padre):
            self.padre = padre

        def generate_content(self, *, model, contents, config=None):
            self.padre.llamadas.append(
                {"model": model, "contents": contents, "config": config}
            )
            if self.padre.error:
                raise self.padre.error
            return type("Respuesta", (), {"text": self.padre.respuesta})()


class BaseTraductor(unittest.TestCase):
    def setUp(self):
        clear_cache()

    def tearDown(self):
        clear_cache()


class TestSinClave(BaseTraductor):
    """Modo de demostración: nunca falla, pero avisa de lo que es."""

    def test_devuelve_una_traduccion_por_texto(self):
        salida = translate(["The export is broken", "It wastes hours"], "es")
        self.assertEqual(len(salida), 2)
        self.assertTrue(all(isinstance(t, Translation) for t in salida))

    def test_se_identifica_como_aproximada_y_offline(self):
        salida = translate(["The export is broken"], "es")
        self.assertEqual(salida[0].engine, "offline")
        self.assertTrue(salida[0].approximate)

    def test_traduce_los_terminos_que_conoce(self):
        salida = translate(["The export is broken"], "es")
        self.assertIn("roto", salida[0].text.lower())

    def test_lo_que_no_conoce_lo_deja_tal_cual(self):
        salida = translate(["Zyzzyva quuxbar"], "es")
        self.assertIn("Zyzzyva", salida[0].text)

    def test_nunca_devuelve_vacio_si_habia_texto(self):
        salida = translate(["algo que no esta en el diccionario"], "es")
        self.assertTrue(salida[0].text.strip())


class TestConClave(BaseTraductor):
    def test_usa_gemini_y_no_marca_aproximada(self):
        cliente = ClienteFalso(respuesta='["La exportacion esta rota"]')
        salida = translate(
            ["The export is broken"],
            "es",
            api_key=CLAVE, model=MODELO,
            client_factory=lambda _k: cliente,
        )
        self.assertEqual(salida[0].text, "La exportacion esta rota")
        self.assertEqual(salida[0].engine, "gemini")
        self.assertFalse(salida[0].approximate)

    def test_una_sola_llamada_para_varias_citas(self):
        cliente = ClienteFalso(respuesta='["uno", "dos", "tres"]')
        translate(
            ["one", "two", "three"],
            "es",
            api_key=CLAVE, model=MODELO,
            client_factory=lambda _k: cliente,
        )
        self.assertEqual(len(cliente.llamadas), 1)

    def test_la_clave_no_viaja_en_el_prompt(self):
        cliente = ClienteFalso(respuesta='["x"]')
        translate(["y"], "es", api_key=CLAVE, model=MODELO, client_factory=lambda _k: cliente)
        self.assertNotIn(CLAVE, str(cliente.llamadas[0]["contents"]))

    def test_el_idioma_destino_llega_al_prompt(self):
        cliente = ClienteFalso(respuesta='["x"]')
        translate(["y"], "en", api_key=CLAVE, model=MODELO, client_factory=lambda _k: cliente)
        contenido = str(cliente.llamadas[0]["contents"]).lower()
        self.assertTrue("english" in contenido or "ingl" in contenido)


class TestCuandoGeminiFalla(BaseTraductor):
    """Un fallo del servicio no puede dejar la interfaz sin texto."""

    def test_si_lanza_cae_al_modo_offline(self):
        cliente = ClienteFalso(error=RuntimeError("503"))
        salida = translate(
            ["The export is broken"],
            "es",
            api_key=CLAVE, model=MODELO,
            client_factory=lambda _k: cliente,
        )
        self.assertEqual(salida[0].engine, "offline")
        self.assertTrue(salida[0].text.strip())

    def test_si_la_respuesta_no_es_json_cae_al_modo_offline(self):
        cliente = ClienteFalso(respuesta="lo siento, no puedo")
        salida = translate(
            ["The export is broken"],
            "es",
            api_key=CLAVE, model=MODELO,
            client_factory=lambda _k: cliente,
        )
        self.assertEqual(salida[0].engine, "offline")

    def test_si_devuelve_otro_numero_de_citas_cae_al_modo_offline(self):
        cliente = ClienteFalso(respuesta='["solo una"]')
        salida = translate(
            ["uno", "dos"],
            "es",
            api_key=CLAVE, model=MODELO,
            client_factory=lambda _k: cliente,
        )
        self.assertEqual(len(salida), 2)
        self.assertEqual(salida[0].engine, "offline")


class TestCache(BaseTraductor):
    def test_no_vuelve_a_llamar_por_el_mismo_texto(self):
        cliente = ClienteFalso(respuesta='["traducido"]')
        for _ in range(3):
            translate(["mismo"], "es", api_key=CLAVE, model=MODELO, client_factory=lambda _k: cliente)
        self.assertEqual(len(cliente.llamadas), 1)

    def test_solo_pide_los_textos_que_faltan(self):
        cliente = ClienteFalso(respuesta='["a"]')
        translate(["uno"], "es", api_key=CLAVE, model=MODELO, client_factory=lambda _k: cliente)

        cliente.respuesta = '["b"]'
        salida = translate(
            ["uno", "dos"], "es", api_key=CLAVE, model=MODELO, client_factory=lambda _k: cliente
        )
        # La segunda llamada solo lleva el texto nuevo.
        self.assertEqual(len(cliente.llamadas), 2)
        self.assertNotIn("uno", str(cliente.llamadas[1]["contents"]))
        self.assertEqual(salida[0].text, "a")
        self.assertEqual(salida[1].text, "b")

    def test_el_idioma_forma_parte_de_la_clave(self):
        cliente = ClienteFalso(respuesta='["es"]')
        translate(["hola"], "es", api_key=CLAVE, model=MODELO, client_factory=lambda _k: cliente)
        cliente.respuesta = '["en"]'
        salida = translate(
            ["hola"], "en", api_key=CLAVE, model=MODELO, client_factory=lambda _k: cliente
        )
        self.assertEqual(len(cliente.llamadas), 2)
        self.assertEqual(salida[0].text, "en")


class TestEntradasRaras(BaseTraductor):
    def test_sin_textos_no_llama_a_nadie(self):
        cliente = ClienteFalso()
        salida = translate([], "es", api_key=CLAVE, model=MODELO, client_factory=lambda _k: cliente)
        self.assertEqual(salida, [])
        self.assertEqual(cliente.llamadas, [])

    def test_un_texto_vacio_se_devuelve_vacio(self):
        salida = translate(["", "   "], "es")
        self.assertEqual([t.text for t in salida], ["", "   "])

    def test_serializa_a_diccionario_para_el_puente(self):
        salida = translate(["The export is broken"], "es")
        datos = salida[0].to_dict()
        self.assertEqual(set(datos), {"text", "engine", "approximate"})


class TestContrato(unittest.TestCase):
    def test_con_clave_hay_que_decir_el_modelo(self):
        """El modelo lo elige quien llama entre los disponibles (F1.2): no
        hay nombre fijo en el traductor al que caer por defecto."""
        with self.assertRaises(ValueError):
            translate(["hola"], "es", api_key=CLAVE)


if __name__ == "__main__":
    unittest.main()
