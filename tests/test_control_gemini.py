"""
Punto único de control de Gemini: una fila por intento (Fase 1, B4)
===================================================================

Decisión de Walter: el presupuesto deja de ser un contador a mano. Cada
intento de llamada (reintentos y fallos incluidos) deja una fila en
`llm_usage` con su propósito, su modelo, sus tokens y su resultado. Antes,
una llamada que fallaba no quedaba en ningún sitio y cada reintento (hasta
4 por petición) era una llamada real que nadie contaba.
"""

import unittest
from typing import ClassVar
from unittest import mock

from core.llm import gemini as gemini_client
from core.llm.control import (
    PROPOSITOS,
    ControlDeGemini,
    Intento,
    RegistroEnMemoria,
    RegistroPostgres,
)
from tests._gemini_dobles import ClienteConCatalogo
from tests._postgres import ADMIN_DSN, borrar_base_de_prueba, postgres_available
from tests.test_gemini_robustness import CLAVE, Guion, cliente, servidor, trozo
from tests.test_llm_provider import respuesta

TEST_DB = "rir_control_gemini_test"


def proveedor(guion, registro, run_id=None):
    control = ControlDeGemini(registro, run_id=run_id)
    return gemini_client.GeminiProvider(CLAVE, control=control, client_factory=guion)


def resumen(registro):
    return [(run, i.purpose, i.outcome, i.error_code, i.input_tokens, i.output_tokens, i.thinking_tokens)
            for run, i in registro.filas]


class ConEsperaFalsa(unittest.TestCase):
    def setUp(self):
        parche = mock.patch.object(gemini_client, "_esperar")
        parche.start()
        self.addCleanup(parche.stop)
        self.registro = RegistroEnMemoria()


class TestUnaFilaPorIntento(ConEsperaFalsa):
    def test_cada_reintento_y_el_exito_dejan_su_fila(self):
        guion = Guion(servidor(503), cliente(429), respuesta("hola", 10, 5, 3))
        texto = proveedor(guion, self.registro, run_id="r1").generate_text(
            "x", model="m", max_output_tokens=64, timeout_ms=1, purpose="otros")
        self.assertEqual(texto, "hola")
        self.assertEqual(resumen(self.registro), [
            ("r1", "otros", "error", "gemini_unavailable", None, None, None),
            ("r1", "otros", "error", "gemini_rate_limited", None, None, None),
            ("r1", "otros", "ok", None, 10, 5, 3),
        ])

    def test_un_fallo_definitivo_tambien_queda(self):
        guion = Guion(cliente(400))
        with self.assertRaises(gemini_client.GeminiError):
            proveedor(guion, self.registro).generate_text(
                "x", model="m", max_output_tokens=64, timeout_ms=1, purpose="otros")
        self.assertEqual([(i.outcome, i.error_code) for _, i in self.registro.filas], [("error", "gemini_error")])

    def test_una_respuesta_bloqueada_cuenta_sus_tokens_como_error(self):
        bloqueada = respuesta("", 7, 0, 0)
        bloqueada.prompt_feedback = trozo(bloqueo="SAFETY").prompt_feedback
        with self.assertRaises(gemini_client.GeminiError):
            proveedor(Guion(bloqueada), self.registro).generate_text(
                "x", model="m", max_output_tokens=64, timeout_ms=1, purpose="otros")
        [(_, intento)] = self.registro.filas
        self.assertEqual((intento.outcome, intento.error_code, intento.input_tokens),
                         ("error", "gemini_blocked", 7))

    def test_el_json_lleva_el_proposito_de_quien_llama(self):
        from pydantic import BaseModel

        class Esquema(BaseModel):
            a: int

        guion = Guion(respuesta('{"a": 1}'))
        proveedor(guion, self.registro).generate_json(
            "x", Esquema, model="m", max_output_tokens=64, timeout_ms=1, purpose="g0")
        self.assertEqual([i.purpose for _, i in self.registro.filas], ["g0"])

    def test_el_stream_y_el_ping_quedan(self):
        p = proveedor(Guion([trozo("hola", "STOP")], [trozo("pong", "STOP")]), self.registro)
        "".join(p.stream_text("x", model="m", max_output_tokens=64, timeout_ms=1, purpose="otros"))
        p.ping(model="m")
        self.assertEqual([(i.purpose, i.outcome) for _, i in self.registro.filas],
                         [("otros", "ok"), ("prueba_clave", "ok")])

    def test_el_listado_de_modelos_queda_sin_tokens(self):
        control = ControlDeGemini(self.registro)
        gemini_client.GeminiProvider(CLAVE, control=control,
                                     client_factory=lambda _k: ClienteConCatalogo()).list_models()
        self.assertEqual(resumen(self.registro), [(None, "listado_modelos", "ok", None, None, None, None)])

    def test_un_proposito_desconocido_no_llega_a_salir(self):
        guion = Guion(respuesta("hola"))
        with self.assertRaises(ValueError):
            proveedor(guion, self.registro).generate_text(
                "x", model="m", max_output_tokens=64, timeout_ms=1, purpose="inventado")
        self.assertEqual((guion.llamadas, self.registro.filas), ([], []))

    def test_los_propositos_son_los_de_la_base(self):
        from pathlib import Path

        sql = (Path(__file__).resolve().parents[1] / "sql" / "migrations" / "017_uso_y_topes_de_gemini.sql")
        for proposito in PROPOSITOS:
            self.assertIn(f"'{proposito}'", sql.read_text("utf-8"))

    def test_la_ejecucion_se_asigna_despues_tambien_a_lo_ya_anotado(self):
        # El re-juicio llama a Gemini antes de crear su ejecución.
        control = ControlDeGemini(self.registro)
        control.anotar(Intento("m", "etiquetado", "ok"))
        control.asignar_ejecucion("r9")
        control.anotar(Intento("m", "g0", "ok"))
        self.assertEqual([run for run, _ in self.registro.filas], ["r9", "r9"])


class TestRegistroDelMotor(unittest.TestCase):
    """El 2026-09-25 la suite escribió 25 filas en el llm_usage real: el listado
    de modelos resolvía el DSN por defecto. El registro lo da ahora el contexto
    del motor (Postgres con persistencia; en memoria sin ella, como sources_state)."""

    def test_el_motor_elige_el_registro_segun_la_persistencia(self):
        from core.orchestration.sidecar_server import _registro_de_uso

        self.assertIsInstance(_registro_de_uso(False, None), RegistroEnMemoria)
        self.assertIsInstance(_registro_de_uso(True, "postgresql://x@localhost/b"), RegistroPostgres)

    def test_listar_modelos_en_los_tests_no_escribe_en_ninguna_base(self):
        from core.orchestration.sidecar.context import SidecarContext
        from tests._sin_red import prohibir_red_real

        prohibir_red_real(self)
        registro = RegistroEnMemoria()
        ctx = SidecarContext(persist_default=False, postgres_dsn=None, env_path=None, started_at=0.0,
                             registro_de_uso=registro)
        with mock.patch("core.llm.gemini._cliente_real", lambda _k: ClienteConCatalogo()):
            ctx.listar_modelos_con_hora("clave", refrescar=True)
        self.assertEqual([(i.purpose, i.outcome) for _, i in registro.filas], [("listado_modelos", "ok")])

    def test_prohibir_red_real_corta_el_registro_en_postgres(self):
        from tests._sin_red import prohibir_red_real

        prohibir_red_real(self)
        with self.assertRaisesRegex(AssertionError, "Base real prohibida"):
            RegistroPostgres("postgresql://x@localhost/b").guardar(None, Intento("m", "otros", "ok"))


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestRegistroPostgres(unittest.TestCase):
    dsn: ClassVar[str]

    @classmethod
    def setUpClass(cls):
        import psycopg

        from scripts.migrate import migrate

        borrar_base_de_prueba(TEST_DB)
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        cls.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")
        from pathlib import Path

        migrate(cls.dsn, Path(__file__).resolve().parents[1] / "sql" / "migrations")

    @classmethod
    def tearDownClass(cls):
        borrar_base_de_prueba(TEST_DB)

    def test_cada_intento_es_una_fila_de_llm_usage(self):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            fila = conn.execute("INSERT INTO radar.pipeline_runs (tenant_id, subreddit_name, trigger_source, status) "
                                "VALUES ('00000000-0000-0000-0000-000000000001', 'p', 'multifuente', 'completed') "
                                "RETURNING id::text").fetchone()
        assert fila is not None
        run = fila[0]
        registro = RegistroPostgres(self.dsn)
        sin_ejecucion = registro.guardar(None, Intento("gemini-x", "etiquetado", "ok", None, 10, 5, 3))
        registro.reasignar([sin_ejecucion], run)
        registro.guardar(None, Intento("gemini-x", "listado_modelos", "error", "gemini_timeout"))
        with psycopg.connect(self.dsn) as conn:
            filas = conn.execute("SELECT run_id::text, model, purpose, outcome, error_code, input_tokens, "
                                 "output_tokens, thinking_tokens FROM radar.llm_usage ORDER BY id").fetchall()
        self.assertEqual(filas, [(run, "gemini-x", "etiquetado", "ok", None, 10, 5, 3),
                                 (None, "gemini-x", "listado_modelos", "error", "gemini_timeout", None, None, None)])


if __name__ == "__main__":
    unittest.main()
