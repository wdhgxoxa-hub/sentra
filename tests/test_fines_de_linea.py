"""
Los archivos que reescriben las herramientas llevan su fin de línea fijado
=========================================================================

`npm run tauri build` reescribe `ui/src-tauri/Cargo.toml` con LF. Con
`core.autocrlf=true` el clon lo saca con CRLF, así que tras cada release el
árbol quedaba con `M ui/src-tauri/Cargo.toml` sin ningún cambio de contenido
(reproducido el 2026-09-24: `git diff` vacío, 2 135 → 2 072 bytes). Con
`eol=lf` el clon y la herramienta escriben los mismos bytes.

Se pregunta a git (`git check-attr`), no al texto de `.gitattributes`: así
cuenta cómo resuelve git los patrones de verdad.
"""

import shutil
import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def atributo(ruta: str, nombre: str) -> str:
    salida = subprocess.run(["git", "check-attr", nombre, "--", ruta], cwd=RAIZ,
                            capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return salida.rsplit(": ", 1)[-1].strip()


@unittest.skipUnless(shutil.which("git"), "sin git")
class TestFinesDeLinea(unittest.TestCase):
    def test_cargo_toml_se_entrega_con_lf(self):
        self.assertEqual(atributo("ui/src-tauri/Cargo.toml", "eol"), "lf")
        self.assertEqual(atributo("ui/src-tauri/Cargo.toml", "text"), "set")


if __name__ == "__main__":
    unittest.main()
