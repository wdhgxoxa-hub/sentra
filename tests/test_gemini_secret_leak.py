"""
La clave de Gemini no sale en ningún texto (AUD-031)
===================================================

El SDK devuelve la clave dentro del detalle de algunos errores. Ninguna
salida de SENTRA puede contenerla: ni la respuesta de un endpoint, ni el
texto en streaming o en JSON, ni la prueba de clave, ni los logs (con traza
incluida).

La clave de prueba tiene la forma real de una clave de Google, pero se
construye en tiempo de ejecución: ningún literal con esa forma llega al
repositorio, que es público.
"""

import io
import logging
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from core.llm import gemini as gemini_client
from core.orchestration.sidecar_server import create_app
from tests._gemini_dobles import control_de_prueba
from tests._sin_red import prohibir_red_real

CLAVE = "AIza" + "Sy" + "Q7x" * 11  # 39 caracteres, forma de clave de Google
OTRA = "AIza" + "Zz" + "k9_" * 11   # una clave distinta que el error pudiera citar


class ErrorDelSdk(Exception):
    """Imita el ClientError del SDK, que repite la URL con ?key=... en el detalle."""


def cliente_que_filtra(api_key):
    class Modelos:
        def generate_content_stream(self, **_kw):
            raise ErrorDelSdk(
                f"400 INVALID_ARGUMENT https://generativelanguage.googleapis.com/"
                f"v1beta/models?key={api_key} also {OTRA}"
            )

        def generate_content(self, **_kw):
            raise ErrorDelSdk(f"403 PERMISSION_DENIED key={api_key}")

        def list(self):
            raise ErrorDelSdk(f"400 API_KEY_INVALID models?key={api_key} {OTRA}")

    class Cliente:
        models = Modelos()

    return Cliente()


class CapturaDeLogs(logging.Handler):
    """Formatea cada registro, traza incluida, como lo escribiría un archivo."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.texto = io.StringIO()
        self.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))

    def emit(self, record):
        self.texto.write(self.format(record) + "\n")


class ConLogs(unittest.TestCase):

    def setUp(self):
        self.captura = CapturaDeLogs()
        raiz = logging.getLogger()
        self.addCleanup(raiz.setLevel, raiz.level)
        raiz.addHandler(self.captura)
        self.addCleanup(raiz.removeHandler, self.captura)
        raiz.setLevel(logging.DEBUG)

    def assertSinClaves(self, *textos):
        for texto in (*textos, self.captura.texto.getvalue()):
            self.assertNotIn(CLAVE, texto)
            self.assertNotIn(OTRA, texto)


class TestFrontera(ConLogs):

    def test_sanear_quita_la_clave_y_cualquier_valor_con_su_forma(self):
        limpio = gemini_client.sanitize(f"fallo con {CLAVE} y {OTRA}", CLAVE)
        self.assertNotIn(CLAVE, limpio)
        self.assertNotIn(OTRA, limpio)

    def test_el_error_del_streaming_no_arrastra_la_clave(self):
        with self.assertRaises(gemini_client.GeminiError) as ctx:
            list(gemini_client.GeminiProvider(CLAVE, control=control_de_prueba(), client_factory=cliente_que_filtra).stream_text(
                "x", model="m", max_output_tokens=64, timeout_ms=1, purpose="otros"))
        self.assertSinClaves(str(ctx.exception), repr(ctx.exception))
        # La excepción original (con la clave) no viaja encadenada.
        self.assertIsNone(ctx.exception.__cause__)
        self.assertTrue(ctx.exception.__suppress_context__)

    def test_listar_modelos_no_la_devuelve(self):
        proveedor = gemini_client.GeminiProvider(CLAVE, control=control_de_prueba(), client_factory=cliente_que_filtra)
        with self.assertRaises(gemini_client.GeminiError) as ctx:
            proveedor.list_models()
        self.assertSinClaves(str(ctx.exception), repr(ctx.exception))

    def test_el_error_del_texto_completo_tampoco_la_arrastra(self):
        proveedor = gemini_client.GeminiProvider(CLAVE, control=control_de_prueba(), client_factory=cliente_que_filtra)
        with self.assertRaises(gemini_client.GeminiError) as ctx:
            proveedor.generate_text("x", model="m", max_output_tokens=64, timeout_ms=1, purpose="otros")
        self.assertSinClaves(str(ctx.exception), repr(ctx.exception))


class TestSidecar(ConLogs):

    def setUp(self):
        prohibir_red_real(self)
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp(prefix="rir_fuga_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.client = TestClient(create_app(insecure_dev=True, persist_default=False,
                                            env_path=str(self.tmp / ".env")))
        self.client.post("/api/gemini", json={"apiKey": CLAVE, "model": "gemini-2.5-flash"})


    def test_la_prueba_por_http_no_la_muestra(self):
        with mock.patch.object(gemini_client, "_cliente_real", cliente_que_filtra):
            respuesta = self.client.post("/api/gemini/test")
        self.assertSinClaves(respuesta.text)


if __name__ == "__main__":
    unittest.main()
