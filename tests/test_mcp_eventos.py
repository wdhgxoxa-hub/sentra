"""
Registro común del escritorio 9 en el servidor MCP
==================================================

Cada `tools/call` que atiende el proceso real (`main`) deja una línea en el
registro común de Claude (`~/Puente/comun/claude_eventos.py`, que el venv ve
por un `.pth`). Aquí el registro va a una carpeta temporal
(`CLAUDE_ESCRITORIO_DIR`) y los datos son falsos. Sin la librería, el servidor
responde igual y no escribe nada.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.mcp import datos as datos_mod
from core.mcp import eventos, servidor
from tests.test_mcp_servidor import DatosFalsos

LLAMADAS = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "estado", "arguments": {}}},
    {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
     "params": {"name": "proponer_escaneo",
                "arguments": {"perfil": {"name": "x", "topic": "café", "keywords": ["café"]},
                              "motivo": "probar"}}},
]


class TestRegistroComun(unittest.TestCase):
    def setUp(self) -> None:
        self.carpeta = Path(tempfile.mkdtemp(prefix="sentra-eventos-"))
        self.addCleanup(shutil.rmtree, self.carpeta, ignore_errors=True)
        entorno = mock.patch.dict(os.environ, {"CLAUDE_ESCRITORIO_DIR": str(self.carpeta)})
        entorno.start()
        self.addCleanup(entorno.stop)

    def _main(self) -> list[dict]:
        entrada = io.StringIO("\n".join(json.dumps(p) for p in LLAMADAS) + "\n")
        salida = io.StringIO()
        with mock.patch.object(datos_mod, "DatosSentra", DatosFalsos), \
                mock.patch.object(sys, "stdin", entrada), mock.patch.object(sys, "stdout", salida):
            self.assertEqual(servidor.main(), 0)
        return [json.loads(linea) for linea in salida.getvalue().splitlines()]

    def _eventos(self) -> list[dict]:
        ruta = self.carpeta / "eventos.jsonl"
        if not ruta.exists():
            return []
        return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]

    def test_cada_llamada_deja_un_evento(self):
        if eventos._ce is None:
            self.skipTest("falta claude_eventos: ~/Puente/scripts/instalar_eventos.sh")
        respuestas = self._main()
        self.assertEqual([r["id"] for r in respuestas], [1, 2, 3, 4])
        estado, propuesta = self._eventos()
        self.assertEqual((estado["herramienta"], estado["tipo"], estado["accion"]), ("sentra", "llamada", "estado"))
        self.assertTrue(estado["ok"])
        self.assertFalse(estado["escribio"])
        self.assertIsInstance(estado["duracion_ms"], int)
        self.assertIn("escaneos", estado["resultado"])
        self.assertEqual(propuesta["accion"], "proponer_escaneo")
        self.assertTrue(propuesta["escribio"])
        self.assertIsNone(propuesta["gasto"])

    def test_sin_la_libreria_el_servidor_sigue_igual(self):
        with mock.patch.object(eventos, "_ce", None):
            respuestas = self._main()
        self.assertEqual([r["id"] for r in respuestas], [1, 2, 3, 4])
        self.assertFalse(respuestas[2]["result"]["isError"])
        self.assertEqual(self._eventos(), [])


if __name__ == "__main__":
    unittest.main()
