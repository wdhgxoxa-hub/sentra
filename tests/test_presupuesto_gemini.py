"""
Configuración › Presupuesto de Gemini (Fase 1, B2 y B4)
=======================================================

Decisión de Walter: los cuatro topes (llamadas y tokens por escaneo y por
día) se editan en Configuración y se guardan en la base
(llm_budget_settings). El aviso de tope alcanzado decía «Súbelo en Ajustes»
cuando ese control no existía: ahora hay un texto por tope que nombra la
ruta real (Configuración › Presupuesto de Gemini › <campo>), y una guardia
comprueba que la sección y el campo nombrados existen en los dos idiomas.
"""

import re
import unittest
from pathlib import Path
from typing import ClassVar
from unittest import mock

from core.llm.control import Topes
from tests._postgres import ADMIN_DSN, borrar_base_de_prueba, postgres_available
from tests.test_sidecar_config import ConfigTestCase

RAIZ = Path(__file__).resolve().parents[1]
I18N = RAIZ / "ui" / "src" / "i18n"
TOPES = {"tope_escaneo_llamadas": "scanCalls", "tope_escaneo_tokens": "scanTokens",
         "tope_diario_llamadas": "dailyCalls", "tope_diario_tokens": "dailyTokens"}
TEST_DB = "rir_presupuesto_gemini_test"


class TestRutas(ConfigTestCase):
    def test_se_leen_los_topes_y_lo_gastado_hoy(self):
        cuerpo = self.client.get("/api/gemini/budget").json()
        self.assertEqual(cuerpo, {"scanMaxCalls": 20, "scanMaxTokens": 500_000, "dailyMaxCalls": 40,
                                  "dailyMaxTokens": 1_000_000, "spentToday": {"calls": 0, "tokens": 0}})

    def test_se_guardan_y_se_vuelven_a_leer(self):
        nuevos = {"scanMaxCalls": 12, "scanMaxTokens": 300_000, "dailyMaxCalls": 30, "dailyMaxTokens": 900_000}
        respuesta = self.client.post("/api/gemini/budget", json=nuevos)
        self.assertEqual(respuesta.status_code, 200, respuesta.text)
        self.assertEqual({k: v for k, v in self.client.get("/api/gemini/budget").json().items()
                          if k != "spentToday"}, nuevos)

    def test_un_tope_negativo_no_se_guarda(self):
        malos = {"scanMaxCalls": -1, "scanMaxTokens": 1, "dailyMaxCalls": 1, "dailyMaxTokens": 1}
        self.assertEqual(self.client.post("/api/gemini/budget", json=malos).status_code, 422)

    def test_un_documento_cortado_por_tope_dice_cual(self):
        from core.llm.base import LLMBudgetExhausted
        from core.orchestration.sidecar import documents

        detalle = {"verdict": "INVESTIGAR MÁS", "rule": "9"}
        corte = LLMBudgetExhausted("tope", motivo="tope_diario_llamadas")
        with mock.patch.object(documents, "_disponible", return_value=True), \
                mock.patch.object(documents, "_cargar", return_value=detalle), \
                mock.patch.object(documents, "_proveedor", return_value=(object(), "m")), \
                mock.patch.object(documents, "generate_document", side_effect=corte):
            respuesta = self.client.post("/api/documents/dossier",
                                         json={"verdictId": "v1", "language": "es", "format": "md"})
        self.assertEqual((respuesta.status_code, respuesta.json()["detail"]["code"]),
                         (429, "tope_diario_llamadas"))


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestTopesEnLaBase(unittest.TestCase):
    dsn: ClassVar[str]

    @classmethod
    def setUpClass(cls):
        import psycopg

        from scripts.migrate import migrate

        borrar_base_de_prueba(TEST_DB)
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        cls.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")
        migrate(cls.dsn, RAIZ / "sql" / "migrations")

    @classmethod
    def tearDownClass(cls):
        borrar_base_de_prueba(TEST_DB)

    def test_guardar_los_topes_los_deja_en_llm_budget_settings(self):
        from core.llm.control import RegistroPostgres

        registro = RegistroPostgres(self.dsn)
        registro.guardar_topes(Topes(5, 6, 7, 8))
        self.assertEqual(registro.topes(), Topes(5, 6, 7, 8))


def bloque(fuente: str, ruta: tuple[str, ...]) -> str:
    """El texto del bloque `a: { b: { ... } }` de un diccionario de i18n."""
    texto = fuente
    for clave in ruta:
        inicio = re.search(rf"\n\s*{clave}: \{{", texto)
        assert inicio is not None, ruta
        texto = texto[inicio.end():]
    return texto


def literal(fuente: str, clave: str) -> str:
    encontrado = re.search(rf"\b{clave}:\s*\n?\s*\"((?:[^\"\\]|\\.)*)\"", fuente)
    assert encontrado is not None, clave
    return encontrado.group(1)


class TestLosAvisosNombranElControlReal(unittest.TestCase):
    def test_cada_tope_tiene_su_texto_con_la_ruta_real(self):
        for idioma in ("es", "en"):
            fuente = (I18N / f"{idioma}.ts").read_text("utf-8")
            vista = literal(bloque(fuente, ("nav",)), "settings")
            presupuesto = bloque(fuente, ("settings", "budget"))
            seccion = literal(presupuesto, "title")
            errores = bloque(fuente, ("errors",))
            for codigo, campo in TOPES.items():
                with self.subTest(idioma=idioma, tope=codigo):
                    ruta = f"{vista} › {seccion} › {literal(presupuesto, campo)}"
                    self.assertIn(ruta, literal(errores, codigo))

    def test_el_aviso_generico_ya_no_manda_a_un_control_que_no_existe(self):
        for idioma in ("es", "en"):
            fuente = (I18N / f"{idioma}.ts").read_text("utf-8")
            vista = literal(bloque(fuente, ("nav",)), "settings")
            seccion = literal(bloque(fuente, ("settings", "budget")), "title")
            with self.subTest(idioma=idioma):
                self.assertIn(f"{vista} › {seccion}", literal(bloque(fuente, ("errors",)), "llm_budget_exhausted"))


if __name__ == "__main__":
    unittest.main()
