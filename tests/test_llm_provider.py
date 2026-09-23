"""
Interfaz LLMProvider y contabilidad de uso (F1.1, F1.5)
=======================================================

Quien pide texto al motor lo hace con parámetros neutros (instrucción de
sistema, límite de salida, timeout); la configuración del SDK se construye
dentro del proveedor. Cada llamada deja constancia de sus tokens (entrada,
salida y razonamiento), del modelo y de la duración, y se carga contra el
presupuesto del escaneo: agotado, la llamada siguiente ni siquiera sale.
"""

import unittest

from google.genai import types

from core.llm.base import LLMBudgetExhausted, LLMProvider, UsageRecord
from core.llm.budget import LLMBudget
from core.llm.gemini import GeminiProvider


def respuesta(texto, entrada=10, salida=5, razonamiento=3):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(
            content=types.Content(parts=[types.Part(text=texto)]),
            finish_reason=types.FinishReason.STOP,
        )],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=entrada,
            candidates_token_count=salida,
            thoughts_token_count=razonamiento,
        ),
    )


class Cliente:
    """Doble con la forma del SDK que guarda cada llamada."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []
        self.models = self

    def __call__(self, _clave):
        return self

    def generate_content(self, **kwargs):
        self.llamadas.append(kwargs)
        return self.respuestas.pop(0)

    def generate_content_stream(self, **kwargs):
        self.llamadas.append(kwargs)
        return iter(self.respuestas.pop(0))


class TestInterfaz(unittest.TestCase):
    def test_gemini_cumple_la_interfaz(self):
        self.assertIsInstance(GeminiProvider("clave"), LLMProvider)

    def test_la_configuracion_del_sdk_la_construye_el_proveedor(self):
        cliente = Cliente(respuesta("hola"))
        texto = GeminiProvider("clave", client_factory=cliente).generate_text(
            "di hola", model="m", system="eres breve", max_output_tokens=64, timeout_ms=5_000,
        )
        self.assertEqual(texto, "hola")
        config = cliente.llamadas[0]["config"]
        self.assertEqual(config.system_instruction, "eres breve")
        self.assertEqual(config.max_output_tokens, 64)
        self.assertEqual(config.http_options.timeout, 5_000)


class TestContabilidad(unittest.TestCase):
    def test_cada_llamada_registra_tokens_modelo_y_duracion(self):
        proveedor = GeminiProvider("clave", client_factory=Cliente(respuesta("a", 10, 5, 3)))
        proveedor.generate_text("x", model="gemini-3.6-flash", max_output_tokens=64, timeout_ms=1)
        registro = proveedor.usage[-1]
        self.assertIsInstance(registro, UsageRecord)
        self.assertEqual(
            (registro.model, registro.input_tokens, registro.output_tokens, registro.reasoning_tokens),
            ("gemini-3.6-flash", 10, 5, 3),
        )
        self.assertGreaterEqual(registro.duration_s, 0)
        self.assertEqual(registro.total_tokens, 18)

    def test_el_streaming_registra_el_uso_del_ultimo_trozo(self):
        trozos = [respuesta("a", 10, 1, 0), respuesta("b", 10, 7, 4)]
        proveedor = GeminiProvider("clave", client_factory=Cliente(trozos))
        texto = "".join(proveedor.stream_text("x", model="m", max_output_tokens=64, timeout_ms=1))
        self.assertEqual(texto, "ab")
        self.assertEqual(proveedor.usage[-1].total_tokens, 21)

    def test_sin_metadatos_de_uso_se_registra_como_desconocido_no_como_cero(self):
        sin_uso = types.GenerateContentResponse(candidates=[types.Candidate(
            content=types.Content(parts=[types.Part(text="a")]),
            finish_reason=types.FinishReason.STOP,
        )])
        proveedor = GeminiProvider("clave", client_factory=Cliente(sin_uso))
        proveedor.generate_text("x", model="m", max_output_tokens=64, timeout_ms=1)
        self.assertIsNone(proveedor.usage[-1].input_tokens)


class TestPresupuesto(unittest.TestCase):
    def test_agotado_el_presupuesto_la_llamada_siguiente_no_sale(self):
        cliente = Cliente(respuesta("a", 10, 5, 3), respuesta("b"))
        presupuesto = LLMBudget(max_tokens=20)
        proveedor = GeminiProvider("clave", client_factory=cliente, budget=presupuesto)
        proveedor.generate_text("x", model="m", max_output_tokens=64, timeout_ms=1)
        self.assertEqual(presupuesto.spent_tokens, 18)

        presupuesto.charge(UsageRecord("m", 5, 0, 0, 0.0))  # 23 > 20
        with self.assertRaises(LLMBudgetExhausted) as ctx:
            proveedor.generate_text("x", model="m", max_output_tokens=64, timeout_ms=1)
        self.assertEqual(ctx.exception.code, "llm_budget_exhausted")
        self.assertEqual(len(cliente.llamadas), 1, "la llamada no debía salir")

    def test_el_presupuesto_por_defecto_es_el_de_d_m4(self):
        self.assertEqual(LLMBudget().max_tokens, 1_000_000)


class TestPing(unittest.TestCase):
    def test_ping_prueba_la_clave_con_el_modelo_indicado(self):
        cliente = Cliente([respuesta("")])
        GeminiProvider("clave", client_factory=cliente).ping(model="gemini-3.6-flash")
        self.assertEqual(cliente.llamadas[0]["model"], "gemini-3.6-flash")


if __name__ == "__main__":
    unittest.main()

