"""
G0: los problemas del grupo son el mismo (residuos de AUD2-001 y AUD2-006)
=========================================================================

Medido con datos reales: la agrupación junta problemas distintos del mismo
tema, y ni la similitud e5 (cruda o centrada) ni los términos compartidos
separan en el conjunto dorado los grupos verdaderos de las mezclas. Solo el
LLM lo distinguía (el abogado del diablo bajó un CONSTRUIR incoherente).
Decisión del usuario: una comprobación por escaneo, en una sola llamada con
todos los grupos y solo sus frases del problema verificadas.

- G0 medida y fallida → DESCARTAR: no es un nicho, es una mezcla.
- G0 sin comprobar (sin proveedor, error, grupo omitido) → nunca CONSTRUIR.
"""

import json
import unittest

from core.judge.coherencia import (
    COHERENCE_VERSION,
    CoherenceGroup,
    CoherenceReport,
    comprobar_coherencia,
    compuerta_coherencia,
)
from core.judge.gates import GateResult, decide
from core.llm.base import LLMError


def compuertas(g0: GateResult | None):
    """G1–G8 aprobadas (con 6 autores): sin G0 saldría CONSTRUIR."""
    todas = [GateResult(f"G{n}", True, 6.0 if n == 2 else 1.0, 1.0, []) for n in range(1, 9)]
    return ([g0] if g0 else []) + todas


class ProveedorDoble:
    def __init__(self, respuesta=None, error=None):
        self.respuesta, self.error, self.prompts = respuesta, error, []

    def generate_json(self, prompt, schema, *, model, max_output_tokens, timeout_ms, system=None,
                      thinking_budget=None):
        assert schema is CoherenceReport
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.respuesta


class TestDecision(unittest.TestCase):
    def test_un_grupo_que_mezcla_problemas_se_descarta(self):
        g0 = compuerta_coherencia(comprobar_coherencia({"a": ["x", "y"]}, provider=ProveedorDoble(
            CoherenceReport(groups=[CoherenceGroup(group_id="a", same_problem=False, reason="mezcla")])),
            model="m")["a"])
        veredicto, regla = decide(compuertas(g0))
        self.assertEqual(veredicto, "DESCARTAR")
        self.assertTrue(regla.startswith("0:"), regla)

    def test_un_mismo_problema_puede_ser_construir(self):
        g0 = compuerta_coherencia(comprobar_coherencia({"a": ["x", "y"]}, provider=ProveedorDoble(
            CoherenceReport(groups=[CoherenceGroup(group_id="a", same_problem=True, reason="igual")])),
            model="m")["a"])
        self.assertEqual(decide(compuertas(g0))[0], "CONSTRUIR")
        self.assertEqual((g0.passed, g0.measured, g0.note), (True, True, "igual"))

    def test_sin_comprobar_nunca_es_construir(self):
        for motivo, resultado in (
                ("sin proveedor", comprobar_coherencia({"a": ["x"]}, provider=None, model=None)),
                ("error", comprobar_coherencia({"a": ["x"]}, provider=ProveedorDoble(
                    error=LLMError("caído")), model="m")),
                ("omitido", comprobar_coherencia({"a": ["x"]}, provider=ProveedorDoble(
                    CoherenceReport(groups=[])), model="m"))):
            with self.subTest(motivo):
                g0 = compuerta_coherencia(resultado["a"])
                self.assertFalse(g0.measured)
                veredicto, regla = decide(compuertas(g0))
                self.assertEqual(veredicto, "INVESTIGAR MÁS")
                self.assertTrue(regla.startswith("8:"), regla)


class TestLectura(unittest.TestCase):
    def test_las_compuertas_guardadas_antes_de_g0_llevan_nota_vacia(self):
        # La interfaz lee `note` en todas; los veredictos anteriores no la traen.
        from core.judge.gates import normalizar_compuertas

        [g] = normalizar_compuertas([{"gate": "G1", "passed": True, "value": 2, "threshold": 2,
                                      "evidence_ids": ["a"], "measured": True}])
        self.assertIsNone(g["note"])


class TestLlamada(unittest.TestCase):
    def test_una_sola_llamada_con_todos_los_grupos_y_solo_sus_frases(self):
        doble = ProveedorDoble(CoherenceReport(groups=[]))
        comprobar_coherencia({"a": ["frase uno", "frase dos"], "b": ["frase tres"]}, provider=doble, model="m")
        self.assertEqual(len(doble.prompts), 1)
        enviado = json.loads(doble.prompts[0][doble.prompts[0].index("{"):])
        self.assertEqual(enviado, {"a": ["frase uno", "frase dos"], "b": ["frase tres"]})

    def test_sin_grupos_no_hay_llamada(self):
        doble = ProveedorDoble(CoherenceReport(groups=[]))
        self.assertEqual(comprobar_coherencia({}, provider=doble, model="m"), {})
        self.assertEqual(doble.prompts, [])

    def test_version(self):
        self.assertEqual(COHERENCE_VERSION, "coherence-v1")


class TestEnElJuez(unittest.TestCase):
    def test_el_juez_descarta_el_grupo_incoherente_y_no_llama_al_abogado(self):
        from core.judge.advocate import AdvocateReport
        from core.judge.dimensions import WEIGHTS_VERSION
        from tests.test_juez_coherente import juzgar, pieza

        class Doble:
            def __init__(self):
                from tests.test_juez_coherente import DobleQueSeEquivoca

                self.base, self.esquemas = DobleQueSeEquivoca(), []

            def generate_json(self, prompt, schema, **kwargs):
                self.esquemas.append(schema)
                if schema is CoherenceReport:
                    grupos = json.loads(prompt[prompt.index("{"):])
                    return CoherenceReport(groups=[CoherenceGroup(group_id=g, same_problem=False, reason="mezcla")
                                                   for g in grupos])
                return self.base.generate_json(prompt, schema, **kwargs)

        quejas = [pieza(n) for n in range(6)]
        vectores = {i.id: [1.0, 0.01 * k, 0.0] for k, i in enumerate(quejas)}
        doble = Doble()
        [veredicto] = juzgar(quejas, vectores, provider=doble).verdicts
        self.assertEqual(veredicto["verdict"], "DESCARTAR")
        self.assertTrue(veredicto["rule"].startswith("0:"))
        g0 = next(g for g in veredicto["gates"] if g["gate"] == "G0")
        self.assertEqual((g0["passed"], g0["measured"], g0["note"]), (False, True, "mezcla"))
        self.assertEqual(doble.esquemas.count(CoherenceReport), 1)
        self.assertNotIn(AdvocateReport, doble.esquemas)
        self.assertEqual(WEIGHTS_VERSION, "judge-weights-v4")


if __name__ == "__main__":
    unittest.main()
