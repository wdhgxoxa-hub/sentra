"""
La CSP deja pasar el IPC de Tauri y nada más
============================================

Tauri 2 habla con Rust por el protocolo propio `ipc:` (en Windows,
`http://ipc.localhost`). Con `default-src 'self'` y sin `connect-src`, la
CSP lo bloqueaba: cada llamada fallaba una vez con un error de consola y
Tauri caía a postMessage (28 errores y 14 recaídas en una sola visita a las
cuatro vistas). La política abre exactamente esos dos orígenes, y ningún
comodín.
"""

import json
import unittest
from pathlib import Path

CONF = Path(__file__).resolve().parents[1] / "ui" / "src-tauri" / "tauri.conf.json"


def directivas() -> dict[str, list[str]]:
    csp = json.loads(CONF.read_text("utf-8"))["app"]["security"]["csp"]
    salida: dict[str, list[str]] = {}
    for trozo in csp.split(";"):
        partes = trozo.split()
        if partes:
            salida[partes[0]] = partes[1:]
    return salida


class TestCsp(unittest.TestCase):
    def test_el_ipc_de_tauri_esta_permitido(self):
        conexion = directivas().get("connect-src", [])
        self.assertIn("ipc:", conexion)
        self.assertIn("http://ipc.localhost", conexion)

    def test_sin_comodines_ni_origenes_de_mas(self):
        for nombre, fuentes in directivas().items():
            self.assertNotIn("*", fuentes, nombre)
            self.assertFalse(any(f.startswith(("https:", "http:*")) and f != "http://ipc.localhost"
                                 for f in fuentes), nombre)
        self.assertEqual(directivas()["default-src"], ["'self'"])


if __name__ == "__main__":
    unittest.main()
