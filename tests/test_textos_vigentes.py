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


class TestTextosVigentes(unittest.TestCase):
    def test_ningun_texto_ofrece_funciones_retiradas(self):
        for idioma in ("es", "en"):
            fuente = (I18N / f"{idioma}.ts").read_text("utf-8")
            # Solo lo que se ve: los literales de texto, no los tipos ni los comentarios.
            textos = re.findall(r'"((?:[^"\\]|\\.)*)"', fuente)
            restos = [t[:90] for t in textos if RETIRADAS.search(t)]
            self.assertEqual(restos, [], idioma)


if __name__ == "__main__":
    unittest.main()
