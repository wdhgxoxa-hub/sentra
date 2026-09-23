"""
Ningún test del sidecar puede salir a la red real
=================================================

Toda clase de test que monta el sidecar (`create_app`) llama a
`prohibir_red_real` o hereda de una que lo hace. Sin esta regla, cuatro
tests llamaron a la API real de Gemini en cuanto la ruta del plan empezó a
listar modelos antes de generar.
"""

import ast
import unittest
from pathlib import Path

from tests._sin_red import prohibir_red_real

RAIZ = Path(__file__).resolve().parent


def _llama(nodo: ast.AST, nombre: str) -> bool:
    return any(
        isinstance(n, ast.Call)
        and (getattr(n.func, "id", None) == nombre or getattr(n.func, "attr", None) == nombre)
        for n in ast.walk(nodo)
    )


def _clases() -> dict[str, tuple[str, ast.ClassDef]]:
    clases: dict[str, tuple[str, ast.ClassDef]] = {}
    for fichero in sorted(RAIZ.glob("test_*.py")):
        for nodo in ast.parse(fichero.read_text(encoding="utf-8")).body:
            if isinstance(nodo, ast.ClassDef):
                clases[f"{fichero.name}:{nodo.name}"] = (fichero.name, nodo)
    return clases


class TestGuardia(unittest.TestCase):
    def test_toda_clase_que_monta_el_sidecar_prohibe_la_red(self):
        clases = _clases()
        por_nombre: dict[str, list[ast.ClassDef]] = {}
        for _, nodo in clases.values():
            por_nombre.setdefault(nodo.name, []).append(nodo)

        def protegida(nodo: ast.ClassDef, vistas: frozenset[str] = frozenset()) -> bool:
            if _llama(nodo, "prohibir_red_real"):
                return True
            for base in nodo.bases:
                nombre = ast.unparse(base).split(".")[-1]
                if nombre in vistas:
                    continue
                if any(protegida(b, vistas | {nombre}) for b in por_nombre.get(nombre, [])):
                    return True
            return False

        for clave, (_, nodo) in clases.items():
            if _llama(nodo, "create_app"):
                with self.subTest(clase=clave):
                    self.assertTrue(protegida(nodo), f"{clave} monta el sidecar sin prohibir la red")

    def test_la_guardia_falla_al_crear_el_cliente_real(self):
        prohibir_red_real(self)
        from core.llm import gemini

        with self.assertRaises(AssertionError):
            gemini._cliente_real("clave")


if __name__ == "__main__":
    unittest.main()
