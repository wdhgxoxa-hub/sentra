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
    return GeminiProvider("clave", client_factory=cliente).generate_json(
        "etiqueta esto", Etiqueta, model="m", max_output_tokens=256, timeout_ms=1,
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


if __name__ == "__main__":
    unittest.main()
