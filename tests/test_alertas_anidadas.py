"""
Una sola alerta por aviso (AUD2-020)
===================================

Sin base de datos, el lector de pantalla anunciaba el aviso dos veces:
DatabaseStatusScreen era un <section role="alert"> que contenía un
ErrorNotice, que ya es role="alert". En pantalla se veía una vez; para quien
usa lector, dos. Ningún componente que pinte un ErrorNotice puede envolverlo
en otra alerta (ErrorBoundary hacía lo mismo con ErrorNoticeView).
"""

import re
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "ui" / "src"


class TestAlertasAnidadas(unittest.TestCase):
    def test_nadie_envuelve_un_error_notice_en_otra_alerta(self):
        culpables = [p.relative_to(UI).as_posix() for p in UI.rglob("*.tsx")
                     if p.name != "ErrorNoticeView.tsx"
                     and re.search(r'role="alert"', (texto := p.read_text("utf-8")))
                     and re.search(r"<ErrorNotice(?:View)?\b", texto)]
        self.assertEqual(culpables, [])


if __name__ == "__main__":
    unittest.main()
