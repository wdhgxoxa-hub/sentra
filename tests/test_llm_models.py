"""
Modelos en vivo (F1.2, F1.3)
============================

Los modelos no se escriben en el código: se piden a la API con la clave del
usuario. De esa lista salen el modelo por defecto (el Flash estable más
reciente de la familia 3.x) y el de documentos (el Pro más reciente
disponible). Si el modelo guardado ya no está, el error es tipado.
"""

import unittest
from types import SimpleNamespace

from core.llm.base import LLMModelUnavailable, ModelInfo
from core.llm.gemini import GeminiProvider, elegir_modelo
from tests._gemini_dobles import control_de_prueba


def modelo(nombre, acciones=("generateContent", "countTokens")):
    """Un modelo tal como lo devuelve `models.list` del SDK."""
    return SimpleNamespace(
        name=f"models/{nombre}",
        display_name=nombre.upper(),
        input_token_limit=1_048_576,
        output_token_limit=65_536,
        supported_actions=list(acciones),
    )


CATALOGO = [
    modelo("gemini-2.5-flash"),
    modelo("gemini-2.5-pro"),
    modelo("gemini-3-flash-preview"),
    modelo("gemini-3.5-flash"),
    modelo("gemini-3.6-flash"),
    modelo("gemini-3.7-flash-preview"),
    modelo("gemini-3.6-flash-lite"),
    modelo("gemini-3.6-flash-image"),
    modelo("gemini-3.6-flash-preview-tts"),
    modelo("gemini-3-pro-preview"),
    modelo("gemini-3.1-pro-preview"),
    modelo("gemini-3.1-pro-preview-customtools"),
    modelo("text-embedding-004", acciones=("embedContent",)),
]


class ClienteConCatalogo:
    def __init__(self, catalogo):
        self.models = SimpleNamespace(list=lambda: iter(catalogo))


def disponibles(catalogo=CATALOGO):
    proveedor = GeminiProvider("clave", control=control_de_prueba(), client_factory=lambda _k: ClienteConCatalogo(catalogo))
    return proveedor.list_models()


class TestListarModelos(unittest.TestCase):
    def test_solo_ofrece_los_que_generan_texto(self):
        ids = [m.id for m in disponibles()]
        self.assertNotIn("text-embedding-004", ids)
        self.assertIn("gemini-3.6-flash", ids)
        self.assertTrue(all(isinstance(m, ModelInfo) for m in disponibles()))

    def test_el_id_no_lleva_el_prefijo_de_la_api(self):
        self.assertTrue(all(not m.id.startswith("models/") for m in disponibles()))


class TestElegirModelo(unittest.TestCase):
    def test_por_defecto_el_flash_estable_mas_reciente_de_la_familia_3(self):
        # Ni el preview más nuevo (3.7), ni variantes (lite, image, tts).
        self.assertEqual(elegir_modelo(disponibles(), "defecto").id, "gemini-3.6-flash")

    def test_para_documentos_el_pro_mas_reciente_aunque_sea_preview(self):
        self.assertEqual(elegir_modelo(disponibles(), "documentos").id, "gemini-3.1-pro-preview")

    def test_a_igual_version_gana_el_estable(self):
        catalogo = [modelo("gemini-3.1-pro-preview"), modelo("gemini-3.1-pro")]
        self.assertEqual(elegir_modelo(disponibles(catalogo), "documentos").id, "gemini-3.1-pro")

    def test_la_familia_2_5_nunca_se_elige(self):
        catalogo = [modelo("gemini-2.5-flash"), modelo("gemini-2.5-pro")]
        for uso in ("defecto", "documentos"):
            with self.subTest(uso=uso), self.assertRaises(LLMModelUnavailable) as ctx:
                elegir_modelo(disponibles(catalogo), uso)
            self.assertEqual(ctx.exception.code, "llm_model_unavailable")

    def test_sin_flash_estable_no_se_inventa_uno(self):
        catalogo = [modelo("gemini-3-flash-preview"), modelo("gemini-3.1-pro-preview")]
        with self.assertRaises(LLMModelUnavailable):
            elegir_modelo(disponibles(catalogo), "defecto")

    def test_el_modelo_guardado_que_desaparece_es_error_tipado(self):
        with self.assertRaises(LLMModelUnavailable) as ctx:
            elegir_modelo(disponibles(), "defecto", guardado="gemini-2.0-flash")
        self.assertIn("gemini-2.0-flash", str(ctx.exception))

    def test_el_modelo_guardado_que_sigue_disponible_se_respeta(self):
        self.assertEqual(
            elegir_modelo(disponibles(), "defecto", guardado="gemini-3.5-flash").id,
            "gemini-3.5-flash",
        )


if __name__ == "__main__":
    unittest.main()
