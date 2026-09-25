"""
Generación estructurada (F1.4)
==============================

`generate_json(schema)` pide al modelo la salida estructurada nativa (JSON
Schema) y además valida la respuesta con Pydantic. Si no valida, un único
reintento con el error de validación en el prompt; si vuelve a fallar,
`LLMInvalidJson`. Nunca se devuelve JSON sin validar.
"""

import json
import unittest

from google.genai import types
from pydantic import BaseModel, Field

from core.llm.base import LLMInvalidJson
from core.llm.gemini import GeminiProvider
from tests._gemini_dobles import control_de_prueba


class Etiqueta(BaseModel):
    is_pain: bool
    confidence: float = Field(ge=0, le=1)
    evidence_span: str | None = None


def respuesta(texto):
    return types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(parts=[types.Part(text=texto)]),
        finish_reason=types.FinishReason.STOP,
    )])


class Cliente:
    def __init__(self, *textos):
        self.textos = list(textos)
        self.llamadas = []
        self.models = self

    def __call__(self, _clave):
        return self

    def generate_content(self, **kwargs):
        self.llamadas.append(kwargs)
        return respuesta(self.textos.pop(0))


def generar(cliente):
    return GeminiProvider("clave", control=control_de_prueba(), client_factory=cliente).generate_json(
        "etiqueta esto", Etiqueta, model="m", max_output_tokens=256, timeout_ms=1, purpose="otros",
    )


VALIDO = json.dumps({"is_pain": True, "confidence": 0.8, "evidence_span": "I hate it"})


class TestGenerateJson(unittest.TestCase):
    def test_pide_la_salida_estructurada_nativa_con_el_esquema(self):
        cliente = Cliente(VALIDO)
        resultado = generar(cliente)
        self.assertEqual(resultado, Etiqueta(is_pain=True, confidence=0.8, evidence_span="I hate it"))
        config = cliente.llamadas[0]["config"]
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertEqual(config.response_json_schema, Etiqueta.model_json_schema())

    def test_si_no_valida_reintenta_una_vez_con_el_error_en_el_prompt(self):
        fuera_de_rango = json.dumps({"is_pain": True, "confidence": 7})
        cliente = Cliente(fuera_de_rango, VALIDO)
        self.assertTrue(generar(cliente).is_pain)
        self.assertEqual(len(cliente.llamadas), 2)
        segundo = str(cliente.llamadas[1]["contents"])
        self.assertIn("confidence", segundo)
        self.assertIn("etiqueta esto", segundo)

    def test_si_vuelve_a_fallar_error_tipado_y_nada_sin_validar(self):
        cliente = Cliente("esto no es json", json.dumps({"confidence": 0.5}))
        with self.assertRaises(LLMInvalidJson) as ctx:
            generar(cliente)
        self.assertEqual(ctx.exception.code, "llm_invalid_json")
        self.assertEqual(len(cliente.llamadas), 2, "un solo reintento")


class TestTruncado(unittest.TestCase):
    """B1: el truncado se detecta explícitamente y no se reintenta en vano."""

    def test_un_json_cortado_es_truncado_y_no_se_reintenta(self):
        from core.llm.base import LLMTruncated

        cliente = Cliente('{"is_pain": true, "confid')
        with self.assertRaises(LLMTruncated):
            generar(cliente)
        self.assertEqual(len(cliente.llamadas), 1, "reintentar con el mismo límite se truncaría igual")

    def test_max_tokens_del_modelo_es_truncado(self):
        from core.llm.base import LLMTruncated

        class Cortado(Cliente):
            def generate_content(self, **kwargs):
                self.llamadas.append(kwargs)
                return types.GenerateContentResponse(candidates=[types.Candidate(
                    content=types.Content(parts=[types.Part(text='{"is_pain": tr')]),
                    finish_reason=types.FinishReason.MAX_TOKENS)])

        with self.assertRaises(LLMTruncated):
            generar(Cortado())


class TestPresupuestoDeRazonamiento(unittest.TestCase):
    """B1: el razonamiento de Gemini 3.x cuenta en max_output_tokens."""

    def test_el_presupuesto_viaja_como_thinking_config(self):
        cliente = Cliente(VALIDO)
        GeminiProvider("clave", control=control_de_prueba(), client_factory=cliente).generate_json(
            "x", Etiqueta, model="m", max_output_tokens=256, timeout_ms=1, purpose="otros", thinking_budget=1024)
        self.assertEqual(cliente.llamadas[0]["config"].thinking_config.thinking_budget, 1024)

    def test_sin_presupuesto_no_se_toca_el_razonamiento(self):
        cliente = Cliente(VALIDO)
        generar(cliente)
        self.assertIsNone(cliente.llamadas[0]["config"].thinking_config)


if __name__ == "__main__":
    unittest.main()
