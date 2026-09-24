"""
Los tests no dejan directorios temporales (R-E)
===============================================

En %TEMP% se acumularon más de cien carpetas rir_* de la suite. La causa:
el directorio se creaba en setUp y se borraba en tearDown, pero unittest
NO llama a tearDown si setUp falla. Cuando AUD-013 hizo que create_app
exigiera token, cada setUp que lo llamaba después de crear su carpeta
fallaba y la dejaba atrás. addCleanup, en cambio, se ejecuta aunque setUp
falle.
"""

import ast
import shutil
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _ejecutar(caso: type[unittest.TestCase]) -> None:
    unittest.TestSuite([caso("test_nada")]).run(unittest.TestResult())


class TestPorQueAddCleanup(unittest.TestCase):
    def test_tear_down_no_limpia_si_set_up_falla(self):
        creadas: list[Path] = []

        class ConTearDown(unittest.TestCase):
            def setUp(self):
                self.tmp = Path(tempfile.mkdtemp(prefix="rir_higiene_"))
                creadas.append(self.tmp)
                raise RuntimeError("setUp falla después de crear la carpeta")

            def tearDown(self):
                shutil.rmtree(self.tmp, ignore_errors=True)

            def test_nada(self):
                pass

        _ejecutar(ConTearDown)
        self.addCleanup(shutil.rmtree, creadas[0], True)
        self.assertTrue(creadas[0].exists(), "tearDown no debería haberse ejecutado")

    def test_add_cleanup_limpia_aunque_set_up_falle(self):
        creadas: list[Path] = []

        class ConAddCleanup(unittest.TestCase):
            def setUp(self):
                self.tmp = Path(tempfile.mkdtemp(prefix="rir_higiene_"))
                self.addCleanup(shutil.rmtree, self.tmp, True)
                creadas.append(self.tmp)
                raise RuntimeError("setUp falla después de crear la carpeta")

            def test_nada(self):
                pass

        _ejecutar(ConAddCleanup)
        self.assertFalse(creadas[0].exists())


def _registra_limpieza(funcion: ast.AST) -> bool:
    """¿La función llama a self.addCleanup(shutil.rmtree, ...)?"""
    for nodo in ast.walk(funcion):
        if (
            isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Attribute)
            and nodo.func.attr == "addCleanup"
            and nodo.args
            and ast.unparse(nodo.args[0]) == "shutil.rmtree"
        ):
            return True
    return False


class TestLaSuiteLimpiaSusCarpetas(unittest.TestCase):
    def test_cada_mkdtemp_registra_su_limpieza_con_add_cleanup(self):
        for fichero in sorted((RAIZ / "tests").glob("test_*.py")):
            if fichero.name == Path(__file__).name:
                continue  # los casos de arriba usan tearDown a propósito
            arbol = ast.parse(fichero.read_text(encoding="utf-8"))
            for funcion in ast.walk(arbol):
                if not isinstance(funcion, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                crea = [
                    n.lineno
                    for n in ast.walk(funcion)
                    if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "mkdtemp"
                ]
                for linea in crea:
                    with self.subTest(fichero=fichero.name, linea=linea):
                        self.assertTrue(
                            _registra_limpieza(funcion),
                            f"{funcion.name} crea un directorio sin addCleanup(shutil.rmtree, ...)",
                        )


class TestNingunTearDown(unittest.TestCase):
    """D2: lo que se deshace (entorno, logging, bases desechables) se registra
    con addCleanup, que se ejecuta aunque setUp falle a medias; tearDown no."""

    def test_ningun_test_define_tear_down(self):
        con_tear_down = []
        for fichero in sorted((RAIZ / "tests").glob("test_*.py")):
            if fichero.name == Path(__file__).name:
                continue  # los casos de arriba usan tearDown a propósito
            for nodo in ast.walk(ast.parse(fichero.read_text(encoding="utf-8"))):
                if isinstance(nodo, ast.FunctionDef) and nodo.name == "tearDown":
                    con_tear_down.append(f"{fichero.name}:{nodo.lineno}")
        self.assertEqual(con_tear_down, [])


if __name__ == "__main__":
    unittest.main()
