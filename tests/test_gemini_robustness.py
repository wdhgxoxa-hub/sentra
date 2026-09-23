"""
Robustez del motor Gemini (AUD-020)
===================================

Ninguno sale a la red. El cliente es un doble con la forma del SDK, y las
respuestas y los errores son los tipos reales de `google.genai`
(`GenerateContentResponse`, `ServerError`, `ClientError`), para que el
código se ejercite contra lo mismo que devuelve Google.

Lo que se comprueba:

- timeout por petición y `max_output_tokens` explícitos;
- reintentos con espera creciente SOLO ante errores transitorios, y nunca
  después de haber entregado texto (repetiría el documento);
- respuesta bloqueada, vacía o cortada por longitud → error tipado, nunca un
  documento vacío dado por bueno;
- el plan sin alguna sección exigida → error tipado con la lista de las que
  faltan, antes de darlo por terminado.
"""

import unittest
from unittest import mock

from google.genai import errors, types

from core.intelligence import gemini_architect
from core.intelligence.gemini_architect import (
    AVISO_DEMO,
    AVISO_DESCONOCIDA,
    SECCIONES_OBLIGATORIAS,
    secciones_ausentes,
    stream_architecture,
)
from core.llm import gemini as gemini_client

CLAVE = "clave-de-prueba"

CLUSTER = {"label": "invoice + manual", "mentionCount": 3, "dataSource": "reddit"}


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


def plan_completo(idioma="es"):
    return "\n\n".join(
        f"{'#' if s.startswith('FASE') else '##'} {s}\n\ncontenido" for s in SECCIONES_OBLIGATORIAS[idioma]
    )


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


def generar(guion, cluster=CLUSTER, idioma="es"):
    return "".join(stream_architecture(cluster, api_key=CLAVE, language=idioma,
                                       client_factory=guion))


class ConEsperaFalsa(unittest.TestCase):

    def setUp(self):
        parche = mock.patch.object(gemini_client, "_esperar")
        self.esperas = parche.start()
        self.addCleanup(parche.stop)


class TestConfiguracion(ConEsperaFalsa):

    def test_cada_peticion_lleva_timeout_y_limite_de_salida(self):
        guion = Guion([trozo(plan_completo(), "STOP")])
        generar(guion)
        config = guion.llamadas[0]["config"]
        self.assertEqual(config.max_output_tokens, gemini_architect.MAX_OUTPUT_TOKENS)
        self.assertEqual(config.http_options.timeout, gemini_architect.TIMEOUT_MS)
        self.assertTrue(config.system_instruction)


class TestReintentos(ConEsperaFalsa):

    def test_un_error_transitorio_se_reintenta_con_espera_creciente(self):
        guion = Guion(servidor(503), cliente(429), [trozo(plan_completo(), "STOP")])
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
        guion = Guion(cliente(400), [trozo(plan_completo(), "STOP")])
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
        # Reintentar repetiría el principio del documento en pantalla.
        guion = Guion([trozo("# FASE 1\n"), servidor(503)], [trozo(plan_completo(), "STOP")])
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
            generar(Guion([trozo("# FASE 1\n"), trozo(fin="SAFETY")]))

    def test_una_respuesta_vacia_no_se_da_por_buena(self):
        for vacia in ([], [trozo(""), trozo(fin="STOP")]):
            with self.assertRaises(gemini_client.GeminiEmpty) as ctx:
                generar(Guion(vacia))
            self.assertEqual(ctx.exception.code, "gemini_empty")

    def test_un_documento_cortado_por_longitud_es_error_tipado(self):
        with self.assertRaises(gemini_client.GeminiTruncated) as ctx:
            generar(Guion([trozo(plan_completo(), "MAX_TOKENS")]))
        self.assertEqual(ctx.exception.code, "gemini_truncated")

    def test_la_traduccion_tambien_detecta_el_bloqueo(self):
        guion = Guion(trozo(bloqueo="PROHIBITED_CONTENT"))
        with self.assertRaises(gemini_client.GeminiBlocked):
            gemini_client.GeminiProvider(CLAVE, client_factory=guion).generate_text(
                "x", model="m", max_output_tokens=64, timeout_ms=1)


class TestEstructura(ConEsperaFalsa):

    def test_un_plan_completo_pasa(self):
        for idioma in ("es", "en"):
            texto = generar(Guion([trozo(plan_completo(idioma), "STOP")]), idioma=idioma)
            self.assertEqual(secciones_ausentes(texto, idioma, "reddit"), [])

    def test_si_faltan_secciones_se_dice_cuales(self):
        incompleto = plan_completo().replace("## Esquema SQL inicial", "## Otra cosa")
        incompleto = incompleto.replace("## Monetización", "")
        with self.assertRaises(gemini_client.GeminiIncomplete) as ctx:
            generar(Guion([trozo(incompleto, "STOP")]))
        self.assertEqual(ctx.exception.code, "gemini_incomplete")
        self.assertEqual(ctx.exception.missing, ["Esquema SQL inicial", "Monetización"])

    def test_los_titulos_se_reconocen_sin_importar_mayusculas_ni_sufijos(self):
        texto = plan_completo().replace("# FASE 1", "# Fase 1: MVP EXPRESS (24-48 h)")
        self.assertEqual(secciones_ausentes(texto, "es", "reddit"), [])

    def test_una_seccion_citada_en_el_cuerpo_no_cuenta_como_titulo(self):
        texto = plan_completo().replace("## Hoja de ruta", "Hoja de ruta")
        self.assertEqual(secciones_ausentes(texto, "es", "reddit"), ["Hoja de ruta"])

    def test_con_demo_el_aviso_inicial_lo_pone_la_aplicacion(self):
        """Con Gemini real, el modelo no copió el aviso letra a letra y el
        plan (43 s, 10/10 secciones) se rechazó. El aviso no puede depender
        de que el modelo obedezca: lo escribe el código."""
        demo = dict(CLUSTER, dataSource="demo")
        for idioma in ("es", "en"):
            texto = generar(Guion([trozo(plan_completo(idioma), "STOP")]), demo, idioma)
            self.assertTrue(texto.startswith(AVISO_DEMO[idioma] + "\n\n"), idioma)
            self.assertEqual(texto.count(AVISO_DEMO[idioma]), 1, idioma)
            self.assertEqual(secciones_ausentes(texto, idioma, "demo"), [], idioma)

    def test_aunque_el_modelo_abra_con_un_titulo_el_aviso_va_delante(self):
        demo = dict(CLUSTER, dataSource="demo")
        con_titulo = "# Plan de arquitectura\n\n" + plan_completo()
        texto = generar(Guion([trozo(con_titulo, "STOP")]), cluster=demo)
        self.assertTrue(texto.startswith(AVISO_DEMO["es"]))

    def test_sin_procedencia_el_aviso_es_el_de_origen_desconocido(self):
        sin_fuente = {k: v for k, v in CLUSTER.items() if k != "dataSource"}
        texto = generar(Guion([trozo(plan_completo(), "STOP")]), cluster=sin_fuente)
        self.assertTrue(texto.startswith(AVISO_DESCONOCIDA["es"] + "\n\n"))

    def test_con_datos_de_reddit_no_hay_aviso(self):
        texto = generar(Guion([trozo(plan_completo(), "STOP")]))
        self.assertEqual(texto, plan_completo())

    def test_si_el_modelo_falla_antes_de_escribir_no_sale_el_aviso_suelto(self):
        demo = dict(CLUSTER, dataSource="demo")
        emitido = []
        with self.assertRaises(gemini_client.GeminiError):
            # extend conserva lo recibido antes de la excepción.
            emitido.extend(stream_architecture(
                demo, api_key=CLAVE, client_factory=Guion(cliente(400)),
            ))
        self.assertEqual(emitido, [])

    def test_las_secciones_exigidas_son_las_que_pide_el_sistema(self):
        for idioma in ("es", "en"):
            sistema, _ = gemini_architect.build_prompt(CLUSTER, idioma)
            for seccion in SECCIONES_OBLIGATORIAS[idioma]:
                self.assertRegex(sistema, rf"(?m)^#+ {seccion}", seccion)


class TestCodigosTraducidos(unittest.TestCase):
    """Cada código con el que puede fallar el plan tiene texto en es y en.

    Llegan a la interfaz como `RadarError::Motor { code }` y los traduce el
    bloque `errors` de i18n (D-A); los códigos propios de Rust los exige
    src-tauri/src/db.rs.
    """

    def codigos(self):
        import re
        from pathlib import Path

        python = {
            clase.code
            for modulo in (gemini_client, gemini_architect)
            for clase in vars(modulo).values()
            if isinstance(clase, type) and issubclass(clase, gemini_client.GeminiError)
        } | {"internal_error"}
        rust = (Path(__file__).resolve().parents[1] / "ui" / "src-tauri" / "src"
                / "commands" / "architect.rs").read_text(encoding="utf-8")
        return python | set(re.findall(r'const CODIGO_\w+: &str = "(\w+)";', rust))

    def test_es_y_en_traducen_todos_los_codigos(self):
        import re
        from pathlib import Path

        codigos = self.codigos()
        self.assertIn("architect_interrupted", codigos)
        self.assertIn("gemini_not_configured", codigos)
        for idioma in ("es", "en"):
            fuente = (Path(__file__).resolve().parents[1] / "ui" / "src" / "i18n"
                      / f"{idioma}.ts").read_text(encoding="utf-8")
            bloque = re.search(r"\n  errors: \{(.*?)\n  \},", fuente, re.DOTALL)
            self.assertIsNotNone(bloque, idioma)
            traducidos = set(re.findall(r"^\s+(\w+):", bloque.group(1), re.MULTILINE))
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
        textos = list(gemini_client.GeminiProvider("clave", client_factory=self.fabrica).stream_text(
            "x", model="m", max_output_tokens=64, timeout_ms=1,
        ))
        self.assertEqual(textos, ["hola"])

    def test_generate_text_llega_a_enviar(self):
        texto = gemini_client.GeminiProvider("clave", client_factory=self.fabrica).generate_text(
            "x", model="m", max_output_tokens=64, timeout_ms=1,
        )
        self.assertEqual(texto, "hola")

    def test_ping_llega_a_enviar(self):
        gemini_client.GeminiProvider("clave", client_factory=self.fabrica).ping(model="m")


if __name__ == "__main__":
    unittest.main()
