"""
Topes de Gemini aplicados en el motor (Fase 1, B4, commit 6)
============================================================

Decisión de Walter: tope por escaneo (llamadas y tokens) y tope diario
(llamadas y tokens, día en hora de Lima), guardados en llm_budget_settings.
El punto de control los comprueba antes de cada intento: al alcanzar uno,
la llamada no sale, queda una fila «cortada» con el motivo en error_code
(con su ejecución: así el motivo queda guardado; pipeline_runs.stop_reason
llega con la migración 018) y se lanza LLMBudgetExhausted. El tope fijo de
1 000 000 de tokens (LLMBudget) desaparece. El listado de modelos se
registra pero no cuenta ni se corta.
"""

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

from core.llm import gemini as gemini_client
from core.llm.base import LLMBudgetExhausted
from core.llm.control import (
    TOPES_POR_DEFECTO,
    ControlDeGemini,
    Intento,
    RegistroEnMemoria,
    Topes,
)
from tests._gemini_dobles import ClienteConCatalogo
from tests._postgres import ADMIN_DSN, borrar_base_de_prueba, postgres_available
from tests.test_llm_provider import Cliente, respuesta

RAIZ = Path(__file__).resolve().parents[1]
TEST_DB = "rir_topes_gemini_test"
#: 2026-09-25 12:00 en Lima (UTC-5).
MEDIODIA = datetime(2026, 9, 25, 17, 0, tzinfo=UTC)


class Reloj:
    def __init__(self, ahora):
        self.ahora = ahora

    def __call__(self):
        return self.ahora


def montar(topes, *, escaneo=True, respuestas=5, reloj=None):
    reloj = reloj or Reloj(MEDIODIA)
    registro = RegistroEnMemoria(topes=topes, reloj=reloj)
    control = ControlDeGemini(registro, run_id="r1", escaneo=escaneo, reloj=reloj)
    cliente = Cliente(*[respuesta("ok", 10, 5, 5) for _ in range(respuestas)])
    proveedor = gemini_client.GeminiProvider("clave", control=control, client_factory=cliente)
    return proveedor, registro, cliente


def llamar(proveedor, purpose="etiquetado"):
    return proveedor.generate_text("x", model="m", max_output_tokens=64, timeout_ms=1, purpose=purpose)


def cortadas(registro):
    return [(run, i.purpose, i.error_code) for run, i in registro.filas if i.outcome == "cortada"]


class TestTopesPorEscaneo(unittest.TestCase):
    def test_al_llegar_al_tope_de_llamadas_la_siguiente_no_sale(self):
        proveedor, registro, cliente = montar(Topes(2, 10**6, 40, 10**6))
        llamar(proveedor)
        llamar(proveedor)
        with self.assertRaises(LLMBudgetExhausted) as error:
            llamar(proveedor)
        self.assertEqual(error.exception.motivo, "tope_escaneo_llamadas")
        self.assertEqual(len(cliente.llamadas), 2)
        self.assertEqual(cortadas(registro), [("r1", "etiquetado", "tope_escaneo_llamadas")])

    def test_al_llegar_al_tope_de_tokens_la_siguiente_no_sale(self):
        proveedor, registro, cliente = montar(Topes(20, 30, 40, 10**6))  # 20 tokens por llamada
        llamar(proveedor)
        llamar(proveedor)  # 40 >= 30: la que ya salió se cobra
        with self.assertRaises(LLMBudgetExhausted):
            llamar(proveedor)
        self.assertEqual(len(cliente.llamadas), 2)
        self.assertEqual(cortadas(registro), [("r1", "etiquetado", "tope_escaneo_tokens")])

    def test_el_control_recuerda_su_primer_motivo_de_corte(self):
        # Con él se rellena pipeline_runs.stop_reason (migración 018).
        proveedor, _, _ = montar(Topes(1, 10**6, 40, 10**6))
        control = proveedor._control
        self.assertIsNone(control.motivo_de_corte)
        llamar(proveedor)
        for _ in range(2):
            with self.assertRaises(LLMBudgetExhausted):
                llamar(proveedor)
        self.assertEqual(control.motivo_de_corte, "tope_escaneo_llamadas")

    def test_un_documento_no_es_un_escaneo(self):
        proveedor, _, cliente = montar(Topes(1, 10**6, 40, 10**6), escaneo=False)
        llamar(proveedor, "dossier")
        llamar(proveedor, "dossier")
        self.assertEqual(len(cliente.llamadas), 2)


class TestTopeDiario(unittest.TestCase):
    def test_lo_gastado_hoy_cuenta_aunque_sea_de_otro_escaneo(self):
        reloj = Reloj(MEDIODIA)
        registro = RegistroEnMemoria(topes=Topes(20, 10**6, 3, 10**6), reloj=reloj)
        for _ in range(3):
            registro.guardar("otro", Intento("m", "etiquetado", "ok", None, 1, 1, 1))
        control = ControlDeGemini(registro, run_id="r2", escaneo=True, reloj=reloj)
        with self.assertRaises(LLMBudgetExhausted) as error:
            control.antes("g0", "m")
        self.assertEqual(error.exception.motivo, "tope_diario_llamadas")

    def test_el_tope_diario_de_tokens(self):
        reloj = Reloj(MEDIODIA)
        registro = RegistroEnMemoria(topes=Topes(20, 10**6, 40, 100), reloj=reloj)
        registro.guardar("otro", Intento("m", "dossier", "ok", None, 60, 30, 10))
        with self.assertRaises(LLMBudgetExhausted) as error:
            ControlDeGemini(registro, reloj=reloj).antes("dossier", "m")
        self.assertEqual(error.exception.motivo, "tope_diario_tokens")

    def test_a_medianoche_de_lima_el_dia_empieza_de_cero(self):
        reloj = Reloj(datetime(2026, 9, 26, 4, 59, tzinfo=UTC))  # 23:59 del 25 en Lima
        registro = RegistroEnMemoria(topes=Topes(20, 10**6, 1, 10**6), reloj=reloj)
        registro.guardar("r", Intento("m", "etiquetado", "ok", None, 1, 1, 1))
        with self.assertRaises(LLMBudgetExhausted):
            ControlDeGemini(registro, reloj=reloj).antes("g0", "m")
        reloj.ahora = datetime(2026, 9, 26, 5, 0, tzinfo=UTC)  # 00:00 del 26 en Lima
        ControlDeGemini(registro, reloj=reloj).antes("g0", "m")

    def test_ni_el_listado_ni_las_cortadas_cuentan(self):
        reloj = Reloj(MEDIODIA)
        registro = RegistroEnMemoria(topes=Topes(20, 10**6, 1, 10**6), reloj=reloj)
        registro.guardar("r", Intento("-", "listado_modelos", "ok"))
        registro.guardar("r", Intento("m", "g0", "cortada", "tope_diario_llamadas"))
        self.assertEqual(registro.uso_de_hoy(MEDIODIA), (0, 0))
        control = ControlDeGemini(registro, reloj=reloj)
        control.antes("g0", "m")

    def test_el_listado_de_modelos_nunca_se_corta(self):
        reloj = Reloj(MEDIODIA)
        registro = RegistroEnMemoria(topes=Topes(0, 0, 0, 0), reloj=reloj)
        control = ControlDeGemini(registro, reloj=reloj)
        gemini_client.GeminiProvider("clave", control=control,
                                     client_factory=lambda _k: ClienteConCatalogo()).list_models()
        self.assertEqual([i.outcome for _, i in registro.filas], ["ok"])


class TestSinTopeFijo(unittest.TestCase):
    def test_el_tope_fijo_de_un_millon_desaparece(self):
        with self.assertRaises(ModuleNotFoundError):
            __import__("core.llm.budget")

    def test_los_topes_por_defecto_son_los_de_la_migracion(self):
        sql = (RAIZ / "sql" / "migrations" / "017_uso_y_topes_de_gemini.sql").read_text("utf-8")
        for columna, valor in zip(("scan_max_calls", "scan_max_tokens", "daily_max_calls", "daily_max_tokens"),
                                  TOPES_POR_DEFECTO, strict=True):
            self.assertIn(f"{columna}{' ' * (18 - len(columna))}integer NOT NULL DEFAULT {valor}", sql)


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestTopesEnPostgres(unittest.TestCase):
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

    def test_los_topes_se_leen_de_la_base(self):
        import psycopg

        from core.llm.control import RegistroPostgres

        with psycopg.connect(self.dsn) as conn:
            conn.execute("UPDATE radar.llm_budget_settings SET daily_max_calls = 7")
        self.assertEqual(RegistroPostgres(self.dsn).topes(), Topes(20, 500_000, 7, 1_000_000))

    def test_el_dia_de_lima_se_cuenta_en_la_base(self):
        import psycopg

        from core.llm.control import RegistroPostgres

        with psycopg.connect(self.dsn) as conn:
            for momento, purpose, outcome in (("2026-09-25 23:59:00-05", "etiquetado", "ok"),
                                              ("2026-09-26 00:00:00-05", "g0", "ok"),
                                              ("2026-09-26 00:01:00-05", "listado_modelos", "ok"),
                                              ("2026-09-26 00:02:00-05", "g0", "cortada")):
                conn.execute("INSERT INTO radar.llm_usage (tenant_id, model, purpose, outcome, input_tokens, "
                             "output_tokens, thinking_tokens, created_at) VALUES "
                             "('00000000-0000-0000-0000-000000000001', 'm', %s, %s, 10, 5, 5, %s)",
                             (purpose, outcome, momento))
        registro = RegistroPostgres(self.dsn)
        self.assertEqual(registro.uso_de_hoy(datetime(2026, 9, 26, 5, 30, tzinfo=UTC)), (1, 20))
        self.assertEqual(registro.uso_de_hoy(datetime(2026, 9, 26, 4, 59, tzinfo=UTC)), (1, 20))
        self.assertEqual(registro.uso_de_hoy(datetime(2026, 9, 26, 4, 59, tzinfo=UTC) - timedelta(days=1)), (0, 0))


if __name__ == "__main__":
    unittest.main()
