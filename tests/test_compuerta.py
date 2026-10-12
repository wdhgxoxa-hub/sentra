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

Migración a Linux: el `python` del sistema es 3.14 y el proyecto fija 3.12.
La compuerta usa el intérprete del proyecto ($PYTHON, si no .venv/bin/python,
si no `python`) para ruff, mypy, los tests, pip-audit y el humo. Estos tests
le pasan un intérprete falso en PYTHON que apunta cada llamada.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
    def correr(self, ruff_sale: int, dobles: tuple[str, ...] = (), pasos: str = "ruff",
               banderas: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        falsos = Path(tempfile.mkdtemp(prefix="compuerta_"))
        self.addCleanup(shutil.rmtree, falsos, True)
        self.registro = falsos / "registro.txt"
        # Intérprete falso: apunta su argv y solo falla `-m ruff` (con ruff_sale).
        (falsos / "python_falso").write_text(
            f'#!/bin/sh\necho "$*" >> "{self.registro.as_posix()}"\n'
            f'[ "$2" = ruff ] && echo "ruff falso" && exit {ruff_sale}\nexit 0\n', newline="\n")
        (falsos / "python_falso").chmod(0o755)
        for doble in dobles:
            (falsos / doble).write_text(f"#!/bin/sh\necho '{doble} falso'\nexit 0\n", newline="\n")
            (falsos / doble).chmod(0o755)
        # Sin las banderas de la compuerta completa: este test corre dentro del hook.
        heredado = {k: v for k, v in os.environ.items() if k not in ("CLIPPY", "AUDIT", "HUMO")}
        entorno = {**heredado, **(banderas or {}), "PASOS": pasos,
                   "PYTHON": str(falsos / "python_falso"),
                   "PATH": f"{falsos}{os.pathsep}{os.environ['PATH']}"}
        ejecutable = bash()
        assert ejecutable is not None  # la clase se salta sin bash
        return subprocess.run([ejecutable, str(COMPUERTA)], cwd=RAIZ, env=entorno,
                              capture_output=True, text=True, encoding="utf-8", check=False)

    def llamadas(self) -> list[str]:
        if not self.registro.exists():
            return []
        return self.registro.read_text("utf-8").splitlines()

    def test_un_paso_que_falla_hace_fallar_la_compuerta(self):
        r = self.correr(3)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("ruff FALLA (rc=3)", r.stdout)
        self.assertIn("COMPUERTA FALLA", r.stdout)

    def test_las_banderas_del_hook_no_llegan_a_la_compuerta_de_prueba(self):
        # El hook exporta CLIPPY=1 AUDIT=1 HUMO=1 y este test corre dentro de él:
        # heredadas, la compuerta de prueba lanzaba otra compuerta con clippy,
        # auditorías y el humo del exe real (PASOS solo limita los pasos por
        # defecto). Intérprete falso y doble de cargo: el rojo no lanza nada real.
        with mock.patch.dict(os.environ, {"CLIPPY": "1", "AUDIT": "1", "HUMO": "1"}):
            r = self.correr(0, dobles=("cargo",))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for paso in ("clippy", "pip-audit", "cargo-audit", "humo"):
            with self.subTest(paso=paso):
                self.assertNotIn(f"{paso} ", r.stdout)

    def test_con_todo_en_verde_sale_con_cero(self):
        r = self.correr(0)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ruff OK", r.stdout)
        self.assertIn("COMPUERTA OK", r.stdout)

    def test_todos_los_pasos_de_python_usan_el_interprete_del_proyecto(self):
        # En Linux el `python` del PATH es 3.14 y no tiene mypy ni pip-audit:
        # ruff, mypy, los tests, pip-audit y el humo van por $PYTHON. Los
        # dobles del PATH no apuntan nada: una llamada desnuda no cuenta y,
        # en rojo, no lanza la suite real (que relanzaría esta compuerta).
        r = self.correr(0, dobles=("cargo", "python", "ruff", "mypy", "pip-audit"),
                        pasos="ruff mypy python", banderas={"AUDIT": "1", "HUMO": "1"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        llamadas = self.llamadas()
        for modulo in ("-m ruff check", "-m mypy", "-W error -m unittest discover",
                       "-m pip_audit", "-m tests.humo_exe"):
            with self.subTest(modulo=modulo):
                self.assertTrue([c for c in llamadas if c.startswith(modulo)], llamadas)
        self.assertEqual(len(llamadas), 5, llamadas)

    def test_los_tests_de_python_corren_con_los_avisos_como_error(self):
        # 0 avisos (2026-10-12): unittest los imprimía y daba OK igual; así se
        # colaron el de Starlette (httpx2) y otros. Con -W error, un aviso es un fallo.
        r = self.correr(0, dobles=("python",), pasos="python")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.llamadas(), ["-W error -m unittest discover -s tests"])

    def test_sin_python_definida_usa_el_venv_si_existe(self):
        texto = COMPUERTA.read_text("utf-8")
        self.assertIn('PY=${PYTHON:-}', texto)
        self.assertIn('.venv/bin/python', texto)


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


@unittest.skipUnless(shutil.which("git"), "sin git")
class TestScriptsEjecutables(unittest.TestCase):
    """ruff EXE001 (shebang sin bit ejecutable) solo mira el bit fuera de
    Windows: en Windows entraron scripts con shebang y modo 100644, y en Linux
    la compuerta caía. Se mira el modo que guarda git, igual en los dos."""

    def test_los_scripts_de_python_con_shebang_son_ejecutables_en_git(self):
        salida = subprocess.run(["git", "ls-files", "-s", "--", "*.py"], cwd=RAIZ, capture_output=True,
                                text=True, encoding="utf-8", check=True).stdout
        sin_bit = []
        for linea in salida.splitlines():
            datos, ruta = linea.split("\t", 1)
            modo = datos.split()[0]
            with (RAIZ / ruta).open("rb") as f:
                if f.read(2) == b"#!" and modo != "100755":
                    sin_bit.append(ruta)
        self.assertEqual(sin_bit, [])

    def test_el_hook_es_ejecutable_en_git(self):
        """Sin el bit, git en Linux salta el hook con un simple aviso y el commit
        entra sin compuerta (en Windows el bit no cuenta)."""
        salida = subprocess.run(["git", "ls-files", "-s", "--", ".githooks/pre-commit"], cwd=RAIZ,
                                capture_output=True, text=True, encoding="utf-8", check=True).stdout
        self.assertTrue(salida.startswith("100755 "), salida)


if __name__ == "__main__":
    unittest.main()
