"""
Los textos de la interfaz describen lo que existe
=================================================

Configuración seguía diciendo que la clave de Gemini activaba «el botón de
arquitectura de cada oportunidad», que el modelo de documentos «escribe el
plan de arquitectura» y que el general «traduce citas»: la ficha de
oportunidad, el Arquitecto y la traducción se retiraron en C2 (D-C3). Un
texto que promete funciones que no hay es la interfaz mintiendo.
"""

import re
import unittest
from pathlib import Path

I18N = Path(__file__).resolve().parents[1] / "ui" / "src" / "i18n"

#: Funciones retiradas que ningún texto visible puede ofrecer.
RETIRADAS = re.compile(
    r"arquitect|architect|oportunidad|opportunit|blueprint|traduce|translat", re.IGNORECASE)


#: AUD2-007: texto sin terminar o de proceso interno que el usuario veía:
#: «Al menos N autores», «(Fase 4)», «la misión no permite… (R7)» y ejemplos
#: de búsqueda de facturas sobre un corpus que no habla de facturas.
SIN_TERMINAR = re.compile(
    r"\bN autores\b|\bN authors\b|\bN/2\b|Fase 4|Phase 4|misi[oó]n|\bmission\b|\(R\d+\)|factura|invoice",
    re.IGNORECASE)

RAIZ = I18N.parents[2]


def literales(fuente: str) -> list[str]:
    """Solo lo que se ve: los literales de texto, no los tipos ni los comentarios."""
    return re.findall(r'"((?:[^"\\]|\\.)*)"', fuente)


#: Tras «en/a» (o «in/to/under») va una vista o un nombre propio. Los que no son
#: vistas se declaran aquí; cualquier otro tiene que estar en la barra (`nav`).
_TRAS_PREPOSICION = {
    "es": re.compile(r"\b(?:en|a) (?:la (?:sección|vista|pantalla) )?«?([A-ZÁÉÍÓÚ][\wáéíóúñ]+)"),
    "en": re.compile(r"\b(?:in|to|under) (?:the )?«?([A-Z]\w+)"),
}
NO_SON_VISTAS = {
    "es": {"Google", "Gemini", "PostgreSQL", "Investigar"},  # «baja a Investigar más»: un veredicto
    "en": {"Google", "Gemini", "PostgreSQL", "Investigate"},
}


def vistas(fuente: str) -> set[str]:
    """Las palabras de las etiquetas de la barra lateral de ese idioma."""
    bloque = re.search(r"\n  nav: \{(.*?)\n  \}", fuente, re.DOTALL)
    assert bloque is not None, "sin bloque nav"
    return {p.lower() for etiqueta in literales(bloque.group(1)) for p in etiqueta.split()}


class TestTextosVigentes(unittest.TestCase):
    def test_los_avisos_solo_mandan_a_vistas_que_existen(self):
        """«Revísala en Ajustes» mandaba a una vista que se llama Configuración."""
        for idioma, patron in _TRAS_PREPOSICION.items():
            fuente = (I18N / f"{idioma}.ts").read_text("utf-8")
            existentes = vistas(fuente)
            inexistentes = sorted({
                f"{nombre}: {texto[:70]}"
                for texto in literales(fuente) for nombre in patron.findall(texto)
                if nombre not in NO_SON_VISTAS[idioma] and nombre.lower() not in existentes
            })
            self.assertEqual(inexistentes, [], idioma)

    def test_ningun_texto_ofrece_funciones_retiradas(self):
        for idioma in ("es", "en"):
            textos = literales((I18N / f"{idioma}.ts").read_text("utf-8"))
            restos = [t[:90] for t in textos if RETIRADAS.search(t)]
            self.assertEqual(restos, [], idioma)

    def test_ningun_texto_esta_sin_terminar_ni_habla_del_proceso(self):
        for idioma in ("es", "en"):
            textos = literales((I18N / f"{idioma}.ts").read_text("utf-8"))
            self.assertEqual([t[:90] for t in textos if SIN_TERMINAR.search(t)], [], idioma)

    def test_los_avisos_de_las_fuentes_hablan_al_usuario(self):
        """pending_approval y los textos de las fuentes llegan tal cual a su tarjeta."""
        from core.sources.catalog import SOURCES

        avisos = [a for fuente in SOURCES for a in (fuente.pending_approval, fuente.cost_model.note) if a]
        self.assertEqual([a for a in avisos if SIN_TERMINAR.search(a)], [])

    def test_las_reglas_del_juez_dicen_sus_numeros(self):
        """La regla del veredicto se enseña tal cual: «G2 por debajo de N/2» no dice nada."""
        from core.judge.gates import decide, evaluate_gates
        from tests.test_judge_verdict import AHORA, grupo_construir

        items, etiquetas = grupo_construir(n=2)
        _, regla = decide(evaluate_gates(items, etiquetas, now=AHORA, min_authors=6), min_authors=6)
        self.assertNotRegex(regla, r"\bN\b")
        self.assertIn("3", regla, "la mitad de 6")


if __name__ == "__main__":
    unittest.main()
