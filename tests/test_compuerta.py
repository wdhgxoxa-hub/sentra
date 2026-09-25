"""
La compuerta vive en el repositorio (AUD2-022, AUD2-021)
=======================================================

La compuerta R3 estaba en la carpeta temporal de una sesión: no la tenía
nadie más y dos commits entraron con ella en rojo. Ahora es
scripts/compuerta.sh y el hook .githooks/pre-commit la ejecuta. Falla si
falla CUALQUIER paso, con el código de salida real de cada herramienta (sin
tuberías que lo oculten). PASOS limita los pasos (lo usan estos tests);
CLIPPY=1, AUDIT=1 y HUMO=1 añaden clippy, las auditorías de dependencias y
la prueba de humo.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
COMPUERTA = RAIZ / "scripts" / "compuerta.sh"


def bash() -> str | None:
    """El bash de Git en Windows: `bash` a secas resuelve al de WSL (System32)."""
    if os.name != "nt":
        return shutil.which("bash")
    git = shutil.which("git")
    for carpeta in Path(git).resolve().parents if git else ():
        if (carpeta / "bin" / "bash.exe").is_file():  # Git\cmd o Git\mingw64\bin → Git\bin
            return str(carpeta / "bin" / "bash.exe")
    return None


@unittest.skipUnless(bash(), "sin bash")
class TestCompuerta(unittest.TestCase):
    def correr(self, ruff_sale: int) -> subprocess.CompletedProcess[str]:
        falsos = Path(tempfile.mkdtemp(prefix="compuerta_"))
        self.addCleanup(shutil.rmtree, falsos, True)
        (falsos / "ruff").write_text(f"#!/bin/sh\necho 'ruff falso'\nexit {ruff_sale}\n", newline="\n")
        entorno = {**os.environ, "PASOS": "ruff", "PATH": f"{falsos}{os.pathsep}{os.environ['PATH']}"}
        ejecutable = bash()
        assert ejecutable is not None  # la clase se salta sin bash
        return subprocess.run([ejecutable, str(COMPUERTA)], cwd=RAIZ, env=entorno,
                              capture_output=True, text=True, encoding="utf-8", check=False)

    def test_un_paso_que_falla_hace_fallar_la_compuerta(self):
        r = self.correr(3)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("ruff FALLA (rc=3)", r.stdout)
        self.assertIn("COMPUERTA FALLA", r.stdout)

    def test_con_todo_en_verde_sale_con_cero(self):
        r = self.correr(0)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ruff OK", r.stdout)
        self.assertIn("COMPUERTA OK", r.stdout)


@unittest.skipUnless(bash() and shutil.which("git"), "sin bash o sin git")
class TestHookCompleto(unittest.TestCase):
    """Regla de Walter (2026-09-24): el repo impone la compuerta COMPLETA en cada
    commit, no solo la reducida. Se ejecuta el hook de verdad en un repo
    temporal cuya compuerta es un doble que dice qué banderas recibió."""

    def correr_hook(self, sale: int) -> subprocess.CompletedProcess[str]:
        repo = Path(tempfile.mkdtemp(prefix="hook_"))
        self.addCleanup(shutil.rmtree, repo, True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "scripts").mkdir()
        (repo / "scripts" / "compuerta.sh").write_text(
            f'#!/usr/bin/env bash\necho "CLIPPY=${{CLIPPY:-}} AUDIT=${{AUDIT:-}} HUMO=${{HUMO:-}}"\nexit {sale}\n',
            newline="\n")
        entorno = {k: v for k, v in os.environ.items() if k not in ("CLIPPY", "AUDIT", "HUMO")}
        ejecutable = bash()
        assert ejecutable is not None  # la clase se salta sin bash
        return subprocess.run([ejecutable, str(RAIZ / ".githooks" / "pre-commit")], cwd=repo,
                              env=entorno, capture_output=True, text=True, encoding="utf-8",
                              check=False)

    def test_el_hook_ejecuta_la_compuerta_completa(self):
        r = self.correr_hook(0)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("CLIPPY=1 AUDIT=1 HUMO=1", r.stdout)

    def test_el_hook_devuelve_el_codigo_real_de_la_compuerta(self):
        self.assertEqual(self.correr_hook(3).returncode, 3)


class TestHookYPasos(unittest.TestCase):

    def test_la_compuerta_tiene_todos_los_pasos(self):
        texto = COMPUERTA.read_text("utf-8")
        for paso in ("ruff", "mypy", "python", "tsc", "node", "cargo", "clippy",
                     "pip-audit", "cargo-audit", "humo"):
            with self.subTest(paso=paso):
                self.assertIn(f"paso {paso} ", texto)

    def test_sin_tuberias_que_oculten_codigos_de_salida(self):
        lineas = [linea for linea in COMPUERTA.read_text("utf-8").splitlines()
                  if linea.strip().startswith(("quiere", "opcional"))]
        self.assertTrue(lineas)
        self.assertFalse([linea for linea in lineas if " | " in linea], lineas)


if __name__ == "__main__":
    unittest.main()
