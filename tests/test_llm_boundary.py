"""
Frontera del motor de IA (F1)
=============================

El SDK del proveedor solo se importa detrás de `core/llm/`. El resto del
código habla con la interfaz `LLMProvider`: cambiar de modelo o de
proveedor no puede obligar a tocar el motor de documentos, el traductor o
el juez.
"""

import ast
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SDK = ("google.genai", "google.generativeai")


def _importa_el_sdk(arbol: ast.AST) -> list[int]:
    lineas = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres = [alias.name for alias in nodo.names]
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            nombres = [nodo.module] + [f"{nodo.module}.{a.name}" for a in nodo.names]
        else:
            continue
        if any(n == s or n.startswith(s + ".") for n in nombres for s in SDK):
            lineas.append(nodo.lineno)
    return lineas


class TestFronteraDelProveedor(unittest.TestCase):
    def test_solo_core_llm_importa_el_sdk(self):
        for carpeta in ("core", "scripts"):
            for fichero in (RAIZ / carpeta).rglob("*.py"):
                if (RAIZ / "core" / "llm") in fichero.parents:
                    continue
                arbol = ast.parse(fichero.read_text(encoding="utf-8"))
                with self.subTest(fichero=str(fichero.relative_to(RAIZ))):
                    self.assertEqual(_importa_el_sdk(arbol), [])

    def test_los_errores_del_proveedor_comparten_base(self):
        from core.llm import gemini
        from core.llm.base import LLMError

        self.assertTrue(issubclass(gemini.GeminiError, LLMError))


if __name__ == "__main__":
    unittest.main()
