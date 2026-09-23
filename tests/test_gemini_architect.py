"""Tests del motor de arquitectura (Gemini).

Ninguno sale a la red: el cliente se inyecta. Lo que se comprueba es lo que
depende de nosotros —qué se le pide al modelo, con qué modelo, y que la clave
no se escape a ningún sitio—, no lo que el modelo responda.
"""

import unittest

from core.intelligence.gemini_architect import (
    AVISO_DEMO,
    AVISO_DESCONOCIDA,
    SECCIONES_OBLIGATORIAS,
    GeminiSinConfigurar,
    build_prompt,
    stream_architecture,
)

CLAVE = "AIzaSy-CLAVE-DE-PRUEBA-NO-REAL"

#: Modelo con el que se llama en los tests: lo elige quien llama (F1.2).
MODELO = "gemini-3.1-pro-preview"

CLUSTER = {
    "clusterKey": "complaint:invoice|manual",
    "label": "invoice + manual",
    "intentType": "complaint",
    "keywords": ["invoice", "manual"],
    "subreddits": ["SaaS", "accounting", "bookkeeping"],
    "mentionCount": 5,
    "communityCount": 3,
    "jobStatement": "Exportar facturas a mano se rompe cada mes",
    "currentSolutions": [],
    "urgencyTier": "HIGH",
    "breakdown": {
        "spreadFactor": 1.0,
        "frequencyFactor": 0.2,
        "severityFactor": 1.0,
        "recencyFactor": 1.0,
        "paidSignalFactor": 1.0,
        "rawScore": 74.0,
        "finalScore": 74.0,
    },
    "evidence": [
        {
            "quote": "I would pay for a tool that fixes this",
            "subreddit": "SaaS",
            "author": "ana",
            "url": "u1",
        },
        {
            "quote": "Reconciling by hand eats a whole day",
            "subreddit": "accounting",
            "author": "luis",
            "url": "u2",
        },
    ],
}


#: Lo que escribe el modelo para CLUSTER: cada sección exigida (AUD-020).
#: El aviso de procedencia no: CLUSTER no registra procedencia y el aviso lo
#: antepone la aplicación (AVISO_INICIAL), no el modelo.
PLAN = "\n\n".join(
    f"## {seccion}\n\ncontenido" for seccion in SECCIONES_OBLIGATORIAS["es"]
)
AVISO_INICIAL = AVISO_DESCONOCIDA["es"] + "\n\n"


class ClienteFalso:
    """Doble del cliente de Gemini, con la misma forma que usa el módulo."""

    def __init__(self, trozos=(PLAN[:40], PLAN[40:]), error=None):
        self.trozos = trozos
        self.error = error
        self.llamadas = []
        self.models = self._Models(self)

    class _Models:
        def __init__(self, padre):
            self.padre = padre

        def generate_content_stream(self, *, model, contents, config=None):
            self.padre.llamadas.append(
                {"model": model, "contents": contents, "config": config}
            )
            if self.padre.error:
                raise self.padre.error
            for texto in self.padre.trozos:
                yield type("Chunk", (), {"text": texto})()


class TestPrompt(unittest.TestCase):
    def test_la_peticion_lleva_la_evidencia_real(self):
        _, peticion = build_prompt(CLUSTER)
        self.assertIn("invoice + manual", peticion)
        self.assertIn("r/accounting", peticion)
        self.assertIn("5", peticion)
        self.assertIn("I would pay for a tool that fixes this", peticion)

    def test_el_sistema_pide_las_dos_fases(self):
        sistema, _ = build_prompt(CLUSTER)
        for exigido in ("FASE 1", "FASE 2", "MVP", "24"):
            self.assertIn(exigido, sistema)

    def test_el_sistema_pide_codigo_y_esquema(self):
        sistema, _ = build_prompt(CLUSTER)
        texto = sistema.lower()
        for exigido in ("sql", "endpoint", "carpeta", "código"):
            self.assertIn(exigido, texto)

    def test_el_prompt_en_ingles_no_deja_espanol(self):
        sistema, peticion = build_prompt(CLUSTER, language="en")
        for palabra in ("Debes", "comunidades", "señal", "construir"):
            self.assertNotIn(palabra, sistema)
            self.assertNotIn(palabra, peticion)

    def test_la_senal_de_pago_llega_al_prompt(self):
        _, alto = build_prompt(CLUSTER)
        sin_pago = dict(CLUSTER, breakdown=dict(CLUSTER["breakdown"], paidSignalFactor=0.0))
        _, bajo = build_prompt(sin_pago)
        self.assertNotEqual(alto, bajo)


def con_fuente(fuente, **stats):
    """El cluster de prueba con su procedencia y, si se dan, sus cifras."""
    return dict(CLUSTER, dataSource=fuente, clusterStats=stats)


#: Frases que afirman que los datos son reales. Solo pueden aparecer cuando
#: la procedencia es Reddit (AUD-017).
AFIRMA_REAL = ("evidencia real", "datos reales", "real evidence", "real data")


class TestProcedencia(unittest.TestCase):
    """El modelo sabe de dónde sale cada dato y cuánto fiarse (AUD-017)."""

    def texto(self, cluster, idioma="es"):
        sistema, peticion = build_prompt(cluster, language=idioma)
        return (sistema + "\n" + peticion).lower()

    def test_con_datos_de_demo_no_se_afirma_que_sean_reales(self):
        for idioma in ("es", "en"):
            texto = self.texto(con_fuente("demo"), idioma)
            for frase in AFIRMA_REAL:
                self.assertNotIn(frase, texto, idioma)

    def test_con_datos_de_demo_se_declara_y_el_aviso_no_se_le_pide_al_modelo(self):
        """El aviso lo pone la aplicación: pedirle al modelo que lo copiara
        letra a letra falló con Gemini real (lo parafraseó o lo movió)."""
        sistema, peticion = build_prompt(con_fuente("demo"))
        self.assertIn("Procedencia: DEMOSTRACIÓN", peticion)
        self.assertIn("no lo repitas", sistema)
        self.assertNotIn(AVISO_DEMO["es"], sistema)
        sistema, peticion = build_prompt(con_fuente("demo"), language="en")
        self.assertIn("Provenance: DEMONSTRATION", peticion)
        self.assertIn("do not repeat it", sistema)
        self.assertNotIn(AVISO_DEMO["en"], sistema)

    def test_sin_procedencia_tampoco_se_afirma_y_se_advierte(self):
        for cluster in (con_fuente(None), CLUSTER):
            sistema, peticion = build_prompt(cluster)
            self.assertIn("Procedencia: desconocida", peticion)
            self.assertIn("no lo repitas", sistema)
            for frase in AFIRMA_REAL:
                self.assertNotIn(frase, (sistema + peticion).lower())

    def test_con_datos_de_reddit_se_declaran_reales_sin_advertencia(self):
        sistema, peticion = build_prompt(con_fuente("reddit"))
        self.assertIn("Procedencia: Reddit", peticion)
        self.assertIn("evidencia real", sistema.lower())
        self.assertNotIn("al inicio del documento", sistema)

    def test_el_dossier_lleva_el_motor_del_clasificador(self):
        _, peticion = build_prompt(con_fuente("reddit", classifier_engines={"heuristic": 5}))
        self.assertIn("Clasificador: heurístico (5 de 5 quejas)", peticion)
        _, peticion = build_prompt(con_fuente(
            "reddit", classifier_engines={"heuristic": 2, "transformers": 3}))
        self.assertIn("heurístico (2 de 5 quejas)", peticion)
        self.assertIn("NLI con transformers (3 de 5 quejas)", peticion)
        _, peticion = build_prompt(con_fuente(
            "reddit", classifier_engines={"heuristic": 5}), language="en")
        self.assertIn("Classifier: heuristic (5 of 5 complaints)", peticion)

    def test_sin_cifras_el_motor_y_las_indeterminadas_constan_como_no_registrados(self):
        _, peticion = build_prompt(con_fuente("reddit"))
        self.assertIn("Clasificador: no registrado", peticion)
        self.assertIn("Gravedad indeterminada: no registrada", peticion)

    def test_el_dossier_lleva_cuantas_etiquetas_son_indeterminadas(self):
        _, peticion = build_prompt(con_fuente("reddit", severity_undetermined=2))
        self.assertIn("Gravedad indeterminada: 2 de 5 quejas", peticion)
        _, peticion = build_prompt(con_fuente("reddit", severity_undetermined=0), language="en")
        self.assertIn("Undetermined severity: 0 of 5 complaints", peticion)

    def test_las_citas_van_numeradas_y_se_exige_citarlas(self):
        for idioma, regla in (("es", "número de cita"), ("en", "quote number")):
            sistema, peticion = build_prompt(con_fuente("reddit"), language=idioma)
            self.assertIn('[1] "I would pay for a tool that fixes this"', peticion)
            self.assertIn('[2] "Reconciling by hand eats a whole day"', peticion)
            self.assertIn(regla, sistema)


class TestStreaming(unittest.TestCase):
    def test_sin_clave_avisa_en_lugar_de_llamar(self):
        with self.assertRaises(GeminiSinConfigurar):
            list(stream_architecture(CLUSTER, model=MODELO, api_key="", client_factory=lambda _k: None))

    def test_devuelve_los_trozos_en_orden(self):
        cliente = ClienteFalso(trozos=(PLAN[:10], PLAN[10:]))
        trozos = list(
            stream_architecture(CLUSTER, model=MODELO, api_key=CLAVE, client_factory=lambda _k: cliente)
        )
        self.assertEqual(trozos, [AVISO_INICIAL, PLAN[:10], PLAN[10:]])

    def test_usa_el_modelo_que_se_le_pide(self):
        cliente = ClienteFalso()
        list(stream_architecture(CLUSTER, model=MODELO, api_key=CLAVE, client_factory=lambda _k: cliente))
        self.assertEqual(cliente.llamadas[0]["model"], MODELO)

        otro = ClienteFalso()
        list(
            stream_architecture(
                CLUSTER, api_key=CLAVE, model="gemini-2.5-flash",
                client_factory=lambda _k: otro,
            )
        )
        self.assertEqual(otro.llamadas[0]["model"], "gemini-2.5-flash")

    def test_manda_la_instruccion_de_sistema(self):
        cliente = ClienteFalso()
        list(stream_architecture(CLUSTER, model=MODELO, api_key=CLAVE, client_factory=lambda _k: cliente))
        config = cliente.llamadas[0]["config"]
        self.assertIn("FASE 1", config.system_instruction)

    def test_la_clave_no_viaja_dentro_del_prompt(self):
        cliente = ClienteFalso()
        list(stream_architecture(CLUSTER, model=MODELO, api_key=CLAVE, client_factory=lambda _k: cliente))
        llamada = cliente.llamadas[0]
        self.assertNotIn(CLAVE, str(llamada["contents"]))
        self.assertNotIn(CLAVE, str(llamada["config"].system_instruction))

    def test_ignora_los_trozos_vacios(self):
        cliente = ClienteFalso(trozos=(PLAN[:5], "", None, PLAN[5:]))
        trozos = list(
            stream_architecture(CLUSTER, model=MODELO, api_key=CLAVE, client_factory=lambda _k: cliente)
        )
        self.assertEqual(trozos, [AVISO_INICIAL, PLAN[:5], PLAN[5:]])


if __name__ == "__main__":
    unittest.main()
