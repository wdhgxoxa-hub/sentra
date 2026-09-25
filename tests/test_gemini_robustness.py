"""
Robustez del motor Gemini (AUD-020)
===================================

Ninguno sale a la red. El cliente es un doble con la forma del SDK, y las
respuestas y los errores son los tipos reales de `google.genai`
(`GenerateContentResponse`, `ServerError`, `ClientError`), para que el
código se ejercite contra lo mismo que devuelve Google.

Lo que se comprueba:

- reintentos con espera creciente SOLO ante errores transitorios, y nunca
  después de haber entregado texto (repetiría lo ya entregado);
- respuesta bloqueada, vacía o cortada por longitud → error tipado, nunca un
  texto vacío dado por bueno;
- cada código de error del proveedor tiene texto en es y en.

Se ejercita el proveedor directamente; el plan de arquitectura por cluster,
por el que antes se probaba, se retiró en C2.
"""

import unittest
from unittest import mock

from google.genai import errors, types

from core.llm import gemini as gemini_client
from tests._ayudas import presente
from tests._gemini_dobles import control_de_prueba

CLAVE = "clave-de-prueba"

#: Un texto cualquiera que el modelo entrega entero.
COMPLETO = "Lógica central: un texto que llega entero."


def trozo(texto=None, fin=None, bloqueo=None):
    """Un trozo del stream tal como lo construye el SDK."""
    candidatos = None
    if texto is not None or fin is not None:
        partes = [types.Part(text=texto)] if texto is not None else []
        candidatos = [types.Candidate(
            content=types.Content(parts=partes),
            finish_reason=getattr(types.FinishReason, fin) if fin else None,
        )]
    feedback = (
        types.GenerateContentResponsePromptFeedback(
            block_reason=getattr(types.BlockedReason, bloqueo))
        if bloqueo else None
    )
    return types.GenerateContentResponse(candidates=candidatos, prompt_feedback=feedback)


def servidor(codigo):
    return errors.ServerError(codigo, {"error": {"code": codigo, "message": "x", "status": "UNAVAILABLE"}})


def cliente(codigo):
    return errors.ClientError(codigo, {"error": {"code": codigo, "message": "x", "status": "X"}})


class Guion:
    """Doble del cliente: cada llamada consume la siguiente respuesta del guion.

    Una respuesta es una excepción (falla al pedir) o una lista de trozos;
    dentro de la lista, una excepción falla a mitad del stream.
    """

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []
        self.models = self

    def __call__(self, _clave):
        return self

    def _siguiente(self, kwargs):
        self.llamadas.append(kwargs)
        respuesta = self.respuestas.pop(0)
        if isinstance(respuesta, BaseException):
            raise respuesta
        return respuesta

    def generate_content_stream(self, **kwargs):
        respuesta = self._siguiente(kwargs)

        def stream():
            for t in respuesta:
                if isinstance(t, BaseException):
                    raise t
                yield t

        return stream()

    def generate_content(self, **kwargs):
        return self._siguiente(kwargs)


def generar(guion):
    """Texto en streaming del proveedor (antes se probaba a través del plan de
    arquitectura, retirado en C2): reintentos y respuestas inservibles."""
    proveedor = gemini_client.GeminiProvider(CLAVE, control=control_de_prueba(), client_factory=guion)
    return "".join(proveedor.stream_text("x", model="m", max_output_tokens=64, timeout_ms=1, purpose="otros"))


class ConEsperaFalsa(unittest.TestCase):

    def setUp(self):
        parche = mock.patch.object(gemini_client, "_esperar")
        self.esperas = parche.start()
        self.addCleanup(parche.stop)


class TestReintentos(ConEsperaFalsa):

    def test_un_error_transitorio_se_reintenta_con_espera_creciente(self):
        guion = Guion(servidor(503), cliente(429), [trozo(COMPLETO, "STOP")])
        self.assertIn("Lógica central", generar(guion))
        self.assertEqual(len(guion.llamadas), 3)
        esperas = [c.args[0] for c in self.esperas.call_args_list]
        self.assertEqual(len(esperas), 2)
        self.assertLess(esperas[0], esperas[1])

    def test_se_rinde_tras_el_maximo_de_reintentos_con_error_tipado(self):
        guion = Guion(*[servidor(503)] * (gemini_client.MAX_RETRIES + 1))
        with self.assertRaises(gemini_client.GeminiUnavailable) as ctx:
            generar(guion)
        self.assertEqual(ctx.exception.code, "gemini_unavailable")
        self.assertEqual(len(guion.llamadas), gemini_client.MAX_RETRIES + 1)

    def test_la_cuota_agotada_tiene_su_codigo(self):
        guion = Guion(*[cliente(429)] * (gemini_client.MAX_RETRIES + 1))
        with self.assertRaises(gemini_client.GeminiRateLimited) as ctx:
            generar(guion)
        self.assertEqual(ctx.exception.code, "gemini_rate_limited")

    def test_un_error_permanente_no_se_reintenta(self):
        guion = Guion(cliente(400), [trozo(COMPLETO, "STOP")])
        with self.assertRaises(gemini_client.GeminiError) as ctx:
            generar(guion)
        self.assertEqual(ctx.exception.code, "gemini_error")
        self.assertEqual(len(guion.llamadas), 1)
        self.esperas.assert_not_called()

    def test_un_timeout_de_red_es_transitorio_y_tiene_su_codigo(self):
        import httpx

        guion = Guion(*[httpx.ReadTimeout("lento")] * (gemini_client.MAX_RETRIES + 1))
        with self.assertRaises(gemini_client.GeminiTimeout) as ctx:
            generar(guion)
        self.assertEqual(ctx.exception.code, "gemini_timeout")
        self.assertEqual(len(guion.llamadas), gemini_client.MAX_RETRIES + 1)

    def test_no_se_reintenta_despues_de_haber_entregado_texto(self):
        # Reintentar repetiría el principio del texto ya entregado.
        guion = Guion([trozo("Lógica\n"), servidor(503)], [trozo(COMPLETO, "STOP")])
        with self.assertRaises(gemini_client.GeminiUnavailable):
            generar(guion)
        self.assertEqual(len(guion.llamadas), 1)


class TestRespuestasInservibles(ConEsperaFalsa):

    def test_una_peticion_bloqueada_por_seguridad_es_error_tipado(self):
        with self.assertRaises(gemini_client.GeminiBlocked) as ctx:
            generar(Guion([trozo(bloqueo="SAFETY")]))
        self.assertEqual(ctx.exception.code, "gemini_blocked")
        self.assertIn("SAFETY", str(ctx.exception))

    def test_una_respuesta_cortada_por_seguridad_es_error_tipado(self):
        with self.assertRaises(gemini_client.GeminiBlocked):
            generar(Guion([trozo("Lógica\n"), trozo(fin="SAFETY")]))

    def test_una_respuesta_vacia_no_se_da_por_buena(self):
        for vacia in ([], [trozo(""), trozo(fin="STOP")]):
            with self.assertRaises(gemini_client.GeminiEmpty) as ctx:
                generar(Guion(vacia))
            self.assertEqual(ctx.exception.code, "gemini_empty")

    def test_un_documento_cortado_por_longitud_es_error_tipado(self):
        with self.assertRaises(gemini_client.GeminiTruncated) as ctx:
            generar(Guion([trozo(COMPLETO, "MAX_TOKENS")]))
        self.assertEqual(ctx.exception.code, "gemini_truncated")

    def test_la_traduccion_tambien_detecta_el_bloqueo(self):
        guion = Guion(trozo(bloqueo="PROHIBITED_CONTENT"))
        with self.assertRaises(gemini_client.GeminiBlocked):
            gemini_client.GeminiProvider(CLAVE, control=control_de_prueba(), client_factory=guion).generate_text(
                "x", model="m", max_output_tokens=64, timeout_ms=1, purpose="otros")


class TestCodigosTraducidos(unittest.TestCase):
    """Cada código con el que puede fallar el plan tiene texto en es y en.

    Llegan a la interfaz como `RadarError::Motor { code }` y los traduce el
    bloque `errors` de i18n (D-A); los códigos propios de Rust los exige
    src-tauri/src/db.rs. También los que el sidecar pone en sus
    `HTTPException` y los de las excepciones de los documentos.
    """

    def codigos(self):
        import re
        from pathlib import Path

        from core.documents import compose
        from core.llm import base

        python = {
            clase.code
            for modulo in (base, gemini_client)
            for clase in vars(modulo).values()
            if isinstance(clase, type) and issubclass(clase, base.LLMError)
        } | {"internal_error", compose.PlanNotRecommended.code}
        raiz = Path(__file__).resolve().parents[1]
        rutas = "\n".join(f.read_text(encoding="utf-8")
                          for f in (raiz / "core" / "orchestration" / "sidecar").glob("*.py"))
        python |= set(re.findall(r'"code": "(\w+)"', rutas))
        comandos = Path(__file__).resolve().parents[1] / "ui" / "src-tauri" / "src" / "commands"
        rust = "\n".join(f.read_text(encoding="utf-8") for f in comandos.glob("*.rs"))
        return python | set(re.findall(r'const CODIGO_\w+: &str = "(\w+)";', rust))

    def test_es_y_en_traducen_todos_los_codigos(self):
        import re
        from pathlib import Path

        codigos = self.codigos()
        self.assertIn("gemini_not_configured", codigos)
        self.assertIn("llm_model_unavailable", codigos)
        self.assertIn("documents_unavailable", codigos)
        for idioma in ("es", "en"):
            fuente = (Path(__file__).resolve().parents[1] / "ui" / "src" / "i18n"
                      / f"{idioma}.ts").read_text(encoding="utf-8")
            bloque = re.search(r"\n  errors: \{(.*?)\n  \},", fuente, re.DOTALL)
            self.assertIsNotNone(bloque, idioma)
            traducidos = set(re.findall(r"^\s+(\w+):", presente(bloque).group(1), re.MULTILINE))
            self.assertEqual(codigos - traducidos, set(), idioma)


class ClienteComoElSdk:
    """Como google.genai.Client: al destruirse cierra el transporte HTTP que
    comparte con `models`, y una petición sobre un transporte cerrado falla.

    Los demás dobles no lo imitan, y por eso pasaba en verde un código que
    creaba el cliente como temporal (`fabrica(clave).models...`): CPython lo
    destruía nada más leer `.models` y ninguna petición real llegaba a salir.
    """

    def __init__(self, respuesta):
        self.transporte = {"cerrado": False}
        self.models = ModelosComoElSdk(self.transporte, respuesta)

    def __del__(self):
        self.transporte["cerrado"] = True


class ModelosComoElSdk:
    def __init__(self, transporte, respuesta):
        self.transporte = transporte
        self.respuesta = respuesta

    def _enviar(self):
        if self.transporte["cerrado"]:
            raise RuntimeError("Cannot send a request, as the client has been closed.")

    def generate_content(self, **_kwargs):
        self._enviar()
        return self.respuesta

    def generate_content_stream(self, **_kwargs):
        self._enviar()

        def stream():
            self._enviar()  # el SDK pide cada trozo por el mismo transporte
            yield self.respuesta

        return stream()


class TestCicloDeVidaDelCliente(ConEsperaFalsa):
    """El cliente del SDK tiene que vivir mientras dure la petición."""

    def fabrica(self, _clave):
        return ClienteComoElSdk(trozo("hola", "STOP"))

    def test_stream_text_llega_a_enviar(self):
        textos = list(gemini_client.GeminiProvider("clave", control=control_de_prueba(), client_factory=self.fabrica).stream_text(
            "x", model="m", max_output_tokens=64, timeout_ms=1, purpose="otros",
        ))
        self.assertEqual(textos, ["hola"])

    def test_generate_text_llega_a_enviar(self):
        texto = gemini_client.GeminiProvider("clave", control=control_de_prueba(), client_factory=self.fabrica).generate_text(
            "x", model="m", max_output_tokens=64, timeout_ms=1, purpose="otros",
        )
        self.assertEqual(texto, "hola")

    def test_ping_llega_a_enviar(self):
        gemini_client.GeminiProvider("clave", control=control_de_prueba(), client_factory=self.fabrica).ping(model="m")


if __name__ == "__main__":
    unittest.main()
