"""
Dependencias declaradas (AUD-021)
=================================

Todo lo que importa el código de producción (core/, scripts/) tiene que
estar en requirements.txt con versión exacta, y lo que importan los tests,
en requirements.txt o requirements-dev.txt. Antes faltaban curl_cffi,
google-genai y toml: una instalación limpia arrancaba y fallaba al primer
uso.

Las importaciones se leen del código (AST), no de una lista a mano. Los
módulos opcionales que el código importa dentro de un try (transformers)
van en requirements-nli.txt, documentados como tales.
"""

import ast
import functools
import re
import sys
import unittest
from importlib import metadata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
LOCALES = {"core", "scripts", "tests"}

#: Módulos que el código importa solo si están (modo degradado sin ellos).
OPCIONALES = {"transformers", "torch"}

#: Distribuciones que dan nombre a un módulo cuyo nombre no coincide o que
#: comparten espacio de nombres (`google` lo ocupan varias).
MODULO_A_DISTRIBUCION = {
    "google": "google-genai",
    "sklearn": "scikit-learn",
    "rank_bm25": "rank-bm25",
    "curl_cffi": "curl_cffi",
}

LINEA = re.compile(r"^([A-Za-z0-9_.\-]+)(\[[^\]]+\])?==([^\s#]+)")


def importados(carpeta: str) -> set[str]:
    modulos: set[str] = set()
    for fichero in (RAIZ / carpeta).rglob("*.py"):
        if "__pycache__" in fichero.parts:
            continue
        for nodo in ast.walk(ast.parse(fichero.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Import):
                nombres = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
                nombres = [nodo.module]
            else:
                continue
            for nombre in nombres:
                raiz = nombre.split(".")[0]
                if raiz not in LOCALES and raiz not in sys.stdlib_module_names:
                    modulos.add(raiz)
    return modulos


def declaradas(archivo: str) -> dict[str, str]:
    """Distribución normalizada → versión exacta, de un requirements."""
    salida: dict[str, str] = {}
    for linea in (RAIZ / archivo).read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        encontrada = LINEA.match(linea)
        if encontrada is None:
            raise AssertionError(f"{archivo}: sin versión exacta: {linea!r}")
        salida[normalizar(encontrada.group(1))] = encontrada.group(3)
    return salida


def normalizar(nombre: str) -> str:
    return re.sub(r"[-_.]+", "-", nombre).lower()


@functools.cache
def _distribuciones() -> dict[str, list[str]]:
    # Recorre todo lo instalado: lento, así que una sola vez.
    return metadata.packages_distributions()


def distribucion(modulo: str) -> str:
    if modulo in MODULO_A_DISTRIBUCION:
        return normalizar(MODULO_A_DISTRIBUCION[modulo])
    candidatas = _distribuciones().get(modulo, [modulo])
    return normalizar(candidatas[0])


class TestDependenciasDeclaradas(unittest.TestCase):

    def test_todo_lo_que_importa_produccion_esta_en_requirements(self):
        produccion = declaradas("requirements.txt")
        for carpeta in ("core", "scripts"):
            for modulo in sorted(importados(carpeta) - OPCIONALES):
                with self.subTest(carpeta=carpeta, modulo=modulo):
                    self.assertIn(distribucion(modulo), produccion)

    def test_lo_que_importan_los_tests_esta_declarado(self):
        todo = {**declaradas("requirements.txt"), **declaradas("requirements-dev.txt")}
        for modulo in sorted(importados("tests") - OPCIONALES):
            with self.subTest(modulo=modulo):
                self.assertIn(distribucion(modulo), todo)

    def test_nada_declarado_sobra_en_produccion(self):
        # Una dependencia que nadie importa se queda instalada por inercia.
        # Las de ejecución indirecta (onnxruntime, motor de fastembed)
        # se justifican en el propio requirements.txt con «# implícita».
        usadas = {distribucion(m) for c in ("core", "scripts") for m in importados(c)}
        implicitas = {
            normalizar(linea.split("==")[0].split("[")[0])
            for linea in (RAIZ / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if "# implícita" in linea
        }
        for nombre in sorted(set(declaradas("requirements.txt")) - usadas - implicitas):
            with self.subTest(dependencia=nombre):
                self.fail(f"{nombre} está declarada pero nada la importa")

    def test_las_opcionales_estan_documentadas_aparte(self):
        texto = (RAIZ / "requirements-nli.txt").read_text(encoding="utf-8")
        for modulo in OPCIONALES:
            self.assertIn(modulo, texto)

    def test_la_version_declarada_es_la_instalada(self):
        # Lo que se verifica en este entorno es lo que se declara.
        for archivo in ("requirements.txt", "requirements-dev.txt"):
            for nombre, version in declaradas(archivo).items():
                with self.subTest(archivo=archivo, dependencia=nombre):
                    self.assertEqual(metadata.version(nombre), version)


if __name__ == "__main__":
    unittest.main()
