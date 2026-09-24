"""
scripts/rejuzgar.py (AUD2-001, 6.4)
==================================

El script solo conecta piezas: el mismo proveedor que usa el escaneo, la
caché de etiquetas en PostgreSQL, los vectores e5 guardados y
core.judge.rejuicio. Aquí se comprueba esa conexión con dobles (ninguna
llamada real) y que informa de cada llamada al LLM con sus tokens: R7 exige
contarlas.
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from core.llm.base import UsageRecord


class ProveedorDoble:
    def __init__(self):
        self.usage = [UsageRecord(model="gemini-x", input_tokens=100, output_tokens=40,
                                  reasoning_tokens=10, duration_s=1.0)]


class TestTopeDeLlamadas(unittest.TestCase):
    """R7 (≤ 15 llamadas en la misión): el re-juicio no puede pasarse. Al tope,
    la llamada no sale y el juez hace lo seguro (sin comprobar → nunca CONSTRUIR)."""

    def test_al_tope_la_llamada_no_sale(self):
        from core.llm.base import LLMBudgetExhausted
        from scripts.rejuzgar import ProveedorConTope

        class Contador:
            def __init__(self):
                self.llamadas, self.usage = 0, []

            def generate_json(self, *args, **kwargs):
                self.llamadas += 1
                return "ok"

        real = Contador()
        con_tope = ProveedorConTope(real, 2)
        self.assertEqual([con_tope.generate_json("p", object()) for _ in range(2)], ["ok", "ok"])
        with self.assertRaises(LLMBudgetExhausted):
            con_tope.generate_json("p", object())
        self.assertEqual(real.llamadas, 2)
        self.assertIs(con_tope.usage, real.usage)

    def test_el_script_aplica_el_tope_pedido(self):
        from scripts import rejuzgar

        proveedor = ProveedorDoble()
        with mock.patch.object(rejuzgar, "_proveedor", return_value=(proveedor, "gemini-x", None)), \
                mock.patch.object(rejuzgar, "_almacen", return_value=mock.Mock(
                    vectors=lambda ids: {}, embed_frases=lambda frases: {})), \
                mock.patch.object(rejuzgar, "rejuzgar", return_value=("run-nueva", {})) as juzgar, \
                redirect_stdout(io.StringIO()):
            rejuzgar.main(["--run", "run-origen", "--max-llamadas", "2"])
        pasado = juzgar.call_args.kwargs["provider"]
        self.assertIsInstance(pasado, rejuzgar.ProveedorConTope)
        self.assertEqual(pasado.maximo, 2)


class TestScriptRejuzgar(unittest.TestCase):
    def test_conecta_el_proveedor_del_escaneo_y_cuenta_las_llamadas(self):
        from scripts import rejuzgar

        proveedor = ProveedorDoble()
        with mock.patch.object(rejuzgar, "_proveedor", return_value=(proveedor, "gemini-x", None)), \
                mock.patch.object(rejuzgar, "_almacen", return_value=mock.Mock(
                    vectors=lambda ids: {}, embed_frases=lambda frases: {})), \
                mock.patch.object(rejuzgar, "rejuzgar", return_value=("run-nueva", {"pain": 3})) as juzgar, \
                redirect_stdout(io.StringIO()) as salida:
            codigo = rejuzgar.main(["--run", "01a0d086-0000-0000-0000-000000000000", "--dsn", "host=x"])
        self.assertEqual(codigo, 0)
        args, kwargs = juzgar.call_args
        self.assertEqual(args, ("host=x", "01a0d086-0000-0000-0000-000000000000"))
        self.assertIs(kwargs["provider"], proveedor)
        self.assertEqual(kwargs["model"], "gemini-x")
        texto = salida.getvalue()
        self.assertIn("run-nueva", texto)
        self.assertIn("llamadas al LLM: 1", texto)
        self.assertIn("100 → 40 (+10 razonamiento)", texto)

    def test_sin_gemini_lo_dice_y_no_rejuzga(self):
        from scripts import rejuzgar

        with mock.patch.object(rejuzgar, "_proveedor", return_value=(None, None, "gemini_not_configured")), \
                mock.patch.object(rejuzgar, "rejuzgar") as juzgar, redirect_stdout(io.StringIO()) as salida:
            codigo = rejuzgar.main(["--run", "x", "--dsn", "host=x"])
        self.assertEqual(codigo, 2)
        juzgar.assert_not_called()
        self.assertIn("gemini_not_configured", salida.getvalue())


if __name__ == "__main__":
    unittest.main()
