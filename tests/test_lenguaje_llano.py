"""
Lenguaje llano en todo lo que se ve (Fase 2, principio P1 de Walter)
====================================================================

Guardia 1: ningún texto de i18n contiene una palabra prohibida
(tests/_lenguaje_llano.py), salvo el bloque `detalle`, que solo se pinta
dentro del desplegable «Ver detalle».
Guardia 2: `t.detalle` solo se usa en `ui/src/components/detalle/`.
Guardia de letra: nada de 10 u 11 px en las pantallas nuevas.

Desde el commit 11 de la Fase 2 se vigilan todos los bloques de i18n salvo
`detalle`, y la letra de toda la interfaz salvo el detalle técnico.
"""

import re
import unittest
from pathlib import Path

from tests._lenguaje_llano import palabras_prohibidas
from tests.test_textos_vigentes import literales

UI = Path(__file__).resolve().parents[1] / "ui" / "src"
I18N = UI / "i18n"

#: El único bloque con jerga permitida: se pinta solo dentro de «Ver detalle».
TECNICO = "detalle"
#: Lo que se pinta solo dentro de «Ver detalle»: puede ir en letra pequeña.
CARPETA_TECNICA = UI / "components" / "detalle"


def bloques(fuente: str) -> dict[str, str]:
    """Bloques de primer nivel del diccionario: `  nombre: { … }` hasta `  },`."""
    return {m.group(1): m.group(2)
            for m in re.finditer(r"\n  (\w+): \{(.*?)\n  \},?", fuente, re.DOTALL)}


class TestLaGuardiaMideBien(unittest.TestCase):
    """Antes de fiarse de la guardia: detecta cada prohibida y deja pasar lo llano."""

    def test_detecta_cada_palabra_prohibida(self):
        casos = {
            "Gasta 5 000 tokens": "tokens", "Falla G7": "G0-G9", "3 clusters": "cluster",
            "la pipeline": "pipeline", "por la regla 9": "regla N", "rule 9 applies": "regla N",
            "el LLM etiqueta": "LLM", "el prompt": "prompt", "Solo APIs oficiales": "API",
            "respuesta JSON": "JSON", "el sidecar": "sidecar", "un uuid": "uuid",
            "embeddings": "embedding", "modelo e5": "e5", "respeta backoff": "backoff",
            "cliente OAuth": "OAuth", "el endpoint": "endpoint", "8 compuertas": "compuerta",
            "passes all gates": "gate", "run 01a0": "run", "runId": "run",
        }
        for texto, esperada in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(palabras_prohibidas(texto), [esperada])

    def test_deja_pasar_el_lenguaje_de_todos_los_dias(self):
        for texto in ("Gemini propone palabras clave", "Buscando en YouTube…", "9 personas distintas",
                      "Genera 1 llamada", "Grupos descartados", "Running out of time? No: «Escanear»",
                      "Gasto de hoy: 2 de 40 llamadas", "The scan found no niches"):
            with self.subTest(texto=texto):
                self.assertEqual(palabras_prohibidas(texto), [])


class TestTextosVisibles(unittest.TestCase):
    def test_ningun_texto_visible_usa_jerga(self):
        for idioma in ("es", "en"):
            fuente = (I18N / f"{idioma}.ts").read_text("utf-8")
            todos = bloques(fuente)
            self.assertIn(TECNICO, todos)
            for nombre in set(todos) - {TECNICO}:
                for literal in literales(todos[nombre]):
                    with self.subTest(idioma=idioma, bloque=nombre, texto=literal):
                        self.assertEqual(palabras_prohibidas(literal), [])

    def test_el_detalle_tecnico_solo_se_pinta_en_ver_detalle(self):
        permitidas = UI / "components" / "detalle"
        for archivo in UI.rglob("*.tsx"):
            if permitidas in archivo.parents:
                continue
            with self.subTest(archivo=archivo.name):
                self.assertNotRegex(archivo.read_text("utf-8"), r"\bt\.detalle\b")

    def test_nada_visible_usa_letra_de_menos_de_12_px(self):
        for archivo in UI.rglob("*.tsx"):
            if CARPETA_TECNICA in archivo.parents:
                continue
            with self.subTest(archivo=archivo.name):
                self.assertNotRegex(archivo.read_text("utf-8"), r"text-\[(?:9|10|11)px\]")

    def test_ningun_enlace_externo_que_la_ventana_no_abriria(self):
        """La ventana no abre enlaces externos: un «Abrir» que no hace nada es la
        interfaz mintiendo. Las direcciones se enseñan en texto seleccionable."""
        for archivo in UI.rglob("*.tsx"):
            with self.subTest(archivo=archivo.name):
                self.assertNotRegex(archivo.read_text("utf-8"), r"<a\s[^>]*href=\{")

    def test_cada_campo_de_cuenta_de_una_fuente_tiene_nombre_llano(self):
        """«api_key», «bearer_token», «client_id»… no se enseñan tal cual."""
        import ast

        from core.sources import registry

        nombres: set[str] = set()
        for archivo in Path(registry.__file__).parent.glob("*.py"):
            for nodo in ast.walk(ast.parse(archivo.read_text("utf-8"))):
                if isinstance(nodo, ast.Call) and getattr(nodo.func, "id", "") == "CredentialField":
                    nombres |= {k.value.value for k in nodo.keywords
                                if k.arg == "name" and isinstance(k.value, ast.Constant)
                                and isinstance(k.value.value, str)}
        self.assertTrue(nombres)
        for idioma in ("es", "en"):
            fuentes = bloques((I18N / f"{idioma}.ts").read_text("utf-8"))["sources"]
            campo = re.search(r"\n    campo: \{(.*?)\n    \}", fuentes, re.DOTALL)
            assert campo is not None, idioma
            definidos = set(re.findall(r"(\w+):", campo.group(1)))
            self.assertEqual(nombres - definidos, set(), idioma)


if __name__ == "__main__":
    unittest.main()
