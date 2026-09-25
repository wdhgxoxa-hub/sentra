"""
La interfaz queda preparada para el modo Videos (Fase 2, principio P2)
======================================================================

Decisión de Walter: no se construye el modo Videos, pero se deja la
interfaz lista para enchufarlo sin rehacer nada. Lo que se puede vigilar sin
pintar la interfaz:

- Las pantallas y los componentes genéricos (asistente, resultado, Radar y
  ficha) no dependen del modo Software: no importan `JudgeVerdict` ni
  `modos/software`; reciben el modo y el nicho ya adaptado.
- La barra lateral reserva el sitio del selector de modo, que se decide
  en `modos/registro.ts` (probado con node: con un modo no se pinta).
"""

import re
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "ui" / "src"
GENERICOS = [UI / "pantallas", UI / "components" / "nicho"]
PROHIBIDO = re.compile(r"\bJudgeVerdict\b|modos/software")


class TestComponentesGenericos(unittest.TestCase):
    def test_las_pantallas_y_el_nicho_no_dependen_del_modo_software(self):
        archivos = [a for carpeta in GENERICOS if carpeta.is_dir() for a in carpeta.rglob("*.tsx")]
        self.assertTrue(archivos, "no hay pantallas genéricas que vigilar")
        for archivo in archivos:
            with self.subTest(archivo=archivo.name):
                self.assertIsNone(PROHIBIDO.search(archivo.read_text("utf-8")))

    def test_la_barra_lateral_reserva_el_sitio_del_selector_de_modo(self):
        barra = (UI / "components" / "Sidebar.tsx").read_text("utf-8")
        self.assertIn("<SelectorDeModo", barra)
        selector = (UI / "components" / "SelectorDeModo.tsx").read_text("utf-8")
        self.assertIn("hayQueElegirModo", selector)


if __name__ == "__main__":
    unittest.main()
