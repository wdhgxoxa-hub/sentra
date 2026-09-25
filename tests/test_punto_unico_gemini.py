"""
Ninguna ruta llama a Gemini saltándose el punto de control (Fase 1, B4)
=======================================================================

Decisión de Walter: ninguna llamada a Gemini puede salir sin pasar por el
único punto de control que la registra y le aplica los topes. Guardia
estática sobre el AST (no sobre el texto: un comentario que nombra
models.list no es una llamada):
- el SDK (google.genai) solo se importa en core/llm/gemini.py;
- generate_content, generate_content_stream y models.list solo se llaman ahí;
- todo GeminiProvider(...) lleva control=... explícito.
Y en ejecución, GeminiProvider sin control no se puede crear.
"""

import ast
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PROVEEDOR = "core/llm/gemini.py"
LLAMADAS_DEL_SDK = frozenset({"generate_content", "generate_content_stream"})


def _nombre(funcion: ast.expr) -> str:
    if isinstance(funcion, ast.Name):
        return funcion.id
    if isinstance(funcion, ast.Attribute):
        return funcion.attr
    return ""


def revisar(fuente: str, ruta: str) -> list[str]:
    """Infracciones del punto único en un fichero de Python."""
    infracciones: list[str] = []
    es_el_proveedor = ruta == PROVEEDOR
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Import | ast.ImportFrom) and not es_el_proveedor:
            modulos = ([a.name for a in nodo.names] if isinstance(nodo, ast.Import)
                       else [f"{nodo.module or ''}.{a.name}" for a in nodo.names])
            if any(m.startswith("google.genai") for m in modulos):
                infracciones.append(f"{ruta}:{nodo.lineno} importa el SDK de Gemini")
        if not isinstance(nodo, ast.Call):
            continue
        funcion = nodo.func
        if not es_el_proveedor and isinstance(funcion, ast.Attribute):
            lista = funcion.attr == "list" and isinstance(funcion.value, ast.Attribute) and funcion.value.attr == "models"
            if funcion.attr in LLAMADAS_DEL_SDK or lista:
                infracciones.append(f"{ruta}:{nodo.lineno} llama al SDK ({funcion.attr}) fuera del proveedor")
        if _nombre(funcion) == "GeminiProvider" and not any(k.arg == "control" for k in nodo.keywords):
            infracciones.append(f"{ruta}:{nodo.lineno} crea GeminiProvider sin control")
    return infracciones


class TestLaGuardiaVe(unittest.TestCase):
    def test_ve_cada_forma_de_saltarse_el_control(self):
        infractor = (
            "from google import genai\n"
            "import google.genai.types\n"
            "c = genai.Client(api_key='x')\n"
            "c.models.generate_content(model='m', contents='x')\n"
            "c.models.generate_content_stream(model='m', contents='x')\n"
            "c.models.list()\n"
            "GeminiProvider('clave')\n"
            "gemini.GeminiProvider('clave', client_factory=f)\n"
        )
        self.assertEqual(len(revisar(infractor, "core/otro.py")), 7, revisar(infractor, "core/otro.py"))

    def test_no_confunde_comentarios_ni_el_proveedor(self):
        limpio = (
            "# cada petición a models.list es una llamada real\n"
            "GeminiProvider('clave', control=self.control())\n"
            "provider.generate_json('x', Esquema, model='m', purpose='g0')\n"
        )
        self.assertEqual(revisar(limpio, "core/otro.py"), [])
        self.assertEqual(revisar("from google import genai\nc.models.list()\n", PROVEEDOR), [])


class TestPuntoUnico(unittest.TestCase):
    def test_nadie_llama_a_gemini_saltandose_el_control(self):
        infracciones = []
        for carpeta in ("core", "scripts"):
            for p in sorted((RAIZ / carpeta).rglob("*.py")):
                ruta = p.relative_to(RAIZ).as_posix()
                infracciones += revisar(p.read_text("utf-8"), ruta)
        self.assertEqual(infracciones, [])

    def test_sin_control_no_hay_proveedor(self):
        from core.llm.gemini import GeminiProvider

        with self.assertRaises(TypeError):
            GeminiProvider("clave")  # type: ignore[call-arg]


if __name__ == "__main__":
    unittest.main()
