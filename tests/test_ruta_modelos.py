"""
El modelo e5 vive en una carpeta de la aplicación, no en %TEMP% (AUD2-010, DP9 A)
================================================================================

fastembed descargaba los 2,1 GB de multilingual-e5-large a su caché por
defecto, dentro de %TEMP%: una limpieza de temporales dejaba sin búsqueda
ni juez hasta volver a descargarlo. La ruta sale de core.rutas.ruta_modelos:
RIR_MODELS_DIR, o %LOCALAPPDATA%/SENTRA/models, o ~/.cache/sentra/models.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import rutas


class TestRutaModelos(unittest.TestCase):
    def entorno(self, **valores):
        base = {k: v for k, v in os.environ.items() if k not in ("RIR_MODELS_DIR", "LOCALAPPDATA")}
        return mock.patch.dict(os.environ, {**base, **valores}, clear=True)

    def test_la_variable_manda(self):
        with self.entorno(RIR_MODELS_DIR="D:/modelos", LOCALAPPDATA="C:/x"):
            self.assertEqual(rutas.ruta_modelos(), Path("D:/modelos"))

    def test_en_windows_la_carpeta_local_de_la_aplicacion(self):
        with self.entorno(LOCALAPPDATA="C:/Users/u/AppData/Local"):
            self.assertEqual(rutas.ruta_modelos(), Path("C:/Users/u/AppData/Local/SENTRA/models"))

    def test_nunca_en_temporales(self):
        with self.entorno():
            self.assertFalse(rutas.ruta_modelos().resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()))

    def test_la_cache_de_modelos_de_gemini_admite_otra_ruta(self):
        # El humo sirve al exe una caché fresca: así no pide la lista a Google
        # ni deja filas en llm_usage. La app real no define la variable.
        with self.entorno(RIR_CACHE_MODELOS="D:/humo/modelos.json", LOCALAPPDATA="C:/x"):
            self.assertEqual(rutas.ruta_cache_modelos_gemini(), Path("D:/humo/modelos.json"))
        with self.entorno(LOCALAPPDATA="C:/x"):
            self.assertEqual(rutas.ruta_cache_modelos_gemini(), Path("C:/x/SENTRA/cache/gemini_models.json"))

    def test_fastembed_recibe_esa_carpeta(self):
        from core.storage.embeddings import FastEmbedEmbedder

        capturado: dict[str, object] = {}

        class Doble:
            def __init__(self, **kwargs):
                capturado.update(kwargs)

            def embed(self, textos):
                return [[0.1, 0.2] for _ in textos]

        with self.entorno(RIR_MODELS_DIR="D:/modelos"), mock.patch("fastembed.TextEmbedding", Doble):
            # Un modelo del catálogo de fastembed: sin registro propio (e5 lo tiene).
            FastEmbedEmbedder("BAAI/bge-small-en-v1.5")
        self.assertEqual(capturado.get("cache_dir"), str(Path("D:/modelos")))


if __name__ == "__main__":
    unittest.main()
