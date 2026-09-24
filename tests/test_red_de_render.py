"""
Ninguna parte de la interfaz queda fuera de una red de render
=============================================================

React desmonta el árbol entero cuando un componente lanza durante el
render: la ventana se queda en negro (el fondo del tema) sin ninguna pista.
Pasó con la barra lateral: el indicador de salud leía un campo que el motor
ya no enviaba, y como solo las vistas iban dentro de un ErrorBoundary, se
caía la aplicación entera. Por eso: la barra lateral lleva su propio límite
y la raíz entera va dentro de otro, de modo que ningún fallo de render deja
la ventana vacía.
"""

import re
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "ui" / "src"


def envuelto(fuente: str, componente: str) -> bool:
    """`<Componente />` está entre un `<ErrorBoundary …>` y su cierre."""
    patron = rf"<ErrorBoundary\b[^>]*>(?:(?!</ErrorBoundary>).)*<{componente}\s*/>.*?</ErrorBoundary>"
    return re.search(patron, fuente, re.DOTALL) is not None


class TestRedDeRender(unittest.TestCase):
    def test_la_raiz_entera_va_dentro_de_un_limite(self):
        self.assertTrue(envuelto((UI / "main.tsx").read_text("utf-8"), "App"))

    def test_la_barra_lateral_tiene_su_propio_limite(self):
        self.assertTrue(envuelto((UI / "App.tsx").read_text("utf-8"), "Sidebar"))


if __name__ == "__main__":
    unittest.main()
