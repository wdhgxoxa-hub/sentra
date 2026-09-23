"""
La clave de Gemini no sale en ningún texto (AUD-031)
===================================================

El SDK devuelve la clave dentro del detalle de algunos errores. Ninguna
salida de SENTRA puede contenerla: ni la respuesta de un endpoint, ni el
documento en streaming, ni la traducción, ni la prueba de clave, ni los
logs (con traza incluida).

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

from core.ingestion.synthetic import SyntheticFetcher
from core.intelligence import gemini_architect, gemini_client, translator
from core.orchestration import RadarDependencies
from core.orchestration.sidecar_server import create_app
from core.storage import HashEmbedder, HybridSearchEngine, LanceDBStore

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
        self.nivel_previo = raiz.level
        raiz.addHandler(self.captura)
        raiz.setLevel(logging.DEBUG)

    def tearDown(self):
        raiz = logging.getLogger()
        raiz.removeHandler(self.captura)
        raiz.setLevel(self.nivel_previo)

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
            list(gemini_architect.stream_architecture(
                {"label": "x"}, api_key=CLAVE, client_factory=cliente_que_filtra))
        self.assertSinClaves(str(ctx.exception), repr(ctx.exception))
        # La excepción original (con la clave) no viaja encadenada.
        self.assertIsNone(ctx.exception.__cause__)
        self.assertTrue(ctx.exception.__suppress_context__)

    def test_la_prueba_de_clave_no_la_devuelve(self):
        ok, detalle = gemini_architect.probe_api_key(CLAVE, client_factory=cliente_que_filtra)
        self.assertFalse(ok)
        self.assertSinClaves(detalle)

    def test_la_traduccion_no_la_deja_en_el_log(self):
        translator.clear_cache()
        resultado = translator.translate(
            ["texto nuevo sin traducir"], "es", api_key=CLAVE, client_factory=cliente_que_filtra)
        self.assertEqual(resultado[0].engine, "offline")
        self.assertSinClaves(resultado[0].text)


class TestSidecar(ConLogs):

    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp(prefix="rir_fuga_"))
        store = LanceDBStore(db_path=str(self.tmp / "lance"), embedder=HashEmbedder(dim=32))
        deps = RadarDependencies(fetcher=SyntheticFetcher(), store=store,
                                 search_engine=HybridSearchEngine(store=store))
        self.client = TestClient(create_app(deps=deps, persist_default=False,
                                            env_path=str(self.tmp / ".env")))
        self.client.post("/api/gemini", json={"apiKey": CLAVE, "model": "gemini-2.5-flash"})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def test_el_documento_en_streaming_no_la_muestra(self):
        with mock.patch.object(gemini_client, "_cliente_real", cliente_que_filtra):
            respuesta = self.client.post(
                "/api/architect/generate", json={"cluster": {"label": "x"}, "language": "es"})
        self.assertSinClaves(respuesta.text)

    def test_la_prueba_por_http_no_la_muestra(self):
        with mock.patch.object(gemini_client, "_cliente_real", cliente_que_filtra):
            respuesta = self.client.post("/api/gemini/test")
        self.assertSinClaves(respuesta.text)

    def test_la_traduccion_por_http_no_la_muestra(self):
        translator.clear_cache()
        with mock.patch.object(gemini_client, "_cliente_real", cliente_que_filtra):
            respuesta = self.client.post(
                "/api/translate", json={"texts": ["otra frase nueva"], "target": "es"})
        self.assertSinClaves(respuesta.text)


if __name__ == "__main__":
    unittest.main()
