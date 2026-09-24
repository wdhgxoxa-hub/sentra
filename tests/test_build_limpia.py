"""
La release compila sin avisos (AUD2-014)
=======================================

`tauri build` avisaba «linker stdout: Creando biblioteca …sentra_lib.dll.lib»
(lint linker_messages): crate-type incluía staticlib y cdylib, herencia de la
plantilla para móvil, y en Windows cdylib genera la biblioteca de importación
de una DLL que nadie usa. SENTRA es de escritorio: el binario solo necesita
rlib. La prueba final es el build de la release sin avisos.
"""

import tomllib
import unittest
from pathlib import Path

CARGO = Path(__file__).resolve().parents[1] / "ui" / "src-tauri" / "Cargo.toml"


class TestBuildLimpia(unittest.TestCase):
    def test_la_biblioteca_es_solo_rlib(self):
        lib = tomllib.loads(CARGO.read_text("utf-8"))["lib"]
        self.assertEqual(lib["crate-type"], ["rlib"])


if __name__ == "__main__":
    unittest.main()
