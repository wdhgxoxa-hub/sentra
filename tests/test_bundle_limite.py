"""
Ningún chunk de la interfaz supera 500 kB (C3)
==============================================

El aviso de Vite se quedaba en aviso y la release salía igual. Ahora el
propio build falla si un chunk pasa del límite (`limite-de-chunks` en
ui/vite.config.ts); el límite no se sube, se divide el código. Aquí se
comprueba que el guardia salta (con un límite de prueba bajo) y que el build
real cabe. Se construye en una carpeta temporal: dist/ no se toca.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "ui"
LIMITE_KB = 500


def construir(salida: Path, limite_kb: int | None = None) -> subprocess.CompletedProcess[str]:
    entorno = dict(os.environ)
    if limite_kb is not None:
        entorno["SENTRA_CHUNK_LIMIT_KB"] = str(limite_kb)
    return subprocess.run(
        f'npx --no-install vite build --outDir "{salida}" --emptyOutDir',
        cwd=UI, shell=True, capture_output=True, text=True, encoding="utf-8", env=entorno,
        timeout=300, check=False,
    )


@unittest.skipUnless(shutil.which("node") and (UI / "node_modules").is_dir(), "sin node o sin node_modules")
class TestLimiteDeChunks(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rir_bundle_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_un_chunk_por_encima_del_limite_rompe_el_build(self):
        resultado = construir(self.tmp / "bajo", limite_kb=50)
        self.assertNotEqual(resultado.returncode, 0, "con 50 kB el build debería fallar")
        self.assertIn("supera el límite", resultado.stdout + resultado.stderr)

    def test_el_build_real_cabe_en_500_kb_por_chunk(self):
        salida = self.tmp / "real"
        resultado = construir(salida)
        self.assertEqual(resultado.returncode, 0, resultado.stdout[-2000:] + resultado.stderr[-2000:])
        tamanos = {p.name: p.stat().st_size for p in (salida / "assets").glob("*.js")}
        self.assertTrue(tamanos)
        grandes = {n: t for n, t in tamanos.items() if t > LIMITE_KB * 1000}
        self.assertEqual(grandes, {})


if __name__ == "__main__":
    unittest.main()
