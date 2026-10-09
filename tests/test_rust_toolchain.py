"""
La cadena de Rust no fija el sistema (migración a Linux)
=======================================================

`rust-toolchain.toml` fijaba `stable-x86_64-pc-windows-msvc`: en Linux rustup
intentaba instalar la cadena de Windows y `cargo` no compilaba. Con el canal
sin triple, cada sistema usa su cadena por defecto: MSVC en Windows (la que
pide WebView2 y la que rustup instala allí por defecto) y GNU en Linux.
"""

import tomllib
import unittest
from pathlib import Path

TOOLCHAIN = Path(__file__).resolve().parents[1] / "ui" / "src-tauri" / "rust-toolchain.toml"


class TestRustToolchain(unittest.TestCase):
    def test_el_canal_es_estable_y_sin_triple_de_sistema(self):
        canal = tomllib.loads(TOOLCHAIN.read_text("utf-8"))["toolchain"]["channel"]
        self.assertEqual(canal, "stable")


if __name__ == "__main__":
    unittest.main()
