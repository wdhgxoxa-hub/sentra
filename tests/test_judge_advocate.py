"""
Juez, etapa 5: abogado del diablo (solo puede bajar)
====================================================

Para cada candidato a CONSTRUIR, el LLM devuelve en JSON los argumentos más
fuertes en contra, cada uno citando ids de evidencia. Regla dura: puede
bajar a INVESTIGAR MÁS con motivo registrado; nunca subir. Los argumentos
que citan ids ajenos al grupo se descartan. Sin abogado (sin proveedor o
con error), un CONSTRUIR sin revisar baja a INVESTIGAR MÁS: un falso
CONSTRUIR es el peor error del sistema.
"""

import unittest
from datetime import UTC, datetime, timedelta

from core.evidence.model import EvidenceItem
from core.judge.advocate import (
    DOWNGRADE_SEVERITIES,
    AdvocateArgument,
    AdvocateReport,
    apply_advocate,
    run_advocate,
)
from core.judge.gates import judge_cluster
from core.judge.labels import VerifiedLabel
from core.llm.base import LLMError
from tests._ayudas import presente

AHORA = datetime(2026, 9, 1, tzinfo=UTC)
FUENTES = ("hackernews", "stackexchange", "github")


def grupo(parche=True):
    items = [EvidenceItem(id=f"{FUENTES[n % 3]}:{n}", source=FUENTES[n % 3], community="c",
                          kind="post", text=f"queja inventada {n}", url=f"https://example.com/{n}",
                          author_hash=f"{n:064x}", created_at=AHORA - timedelta(days=5),
                          fetched_at=AHORA, data_source="real") for n in range(10)]
    etiquetas = {i.id: VerifiedLabel(item_id=i.id, content_hash="h", labeler="t", is_pain="yes",
                                     intent="queja", workaround_described="no", wtp_signal="no")
                 for i in items}
    etiquetas[items[0].id] = etiquetas[items[0].id].model_copy(
        update={"workaround_described": "yes" if parche else "no"})
    etiquetas[items[1].id] = etiquetas[items[1].id].model_copy(update={"wtp_signal": "yes"})
    return items, etiquetas


class LLMAbogado:
    def __init__(self, informe=None, error=None):
        self.informe, self.error, self.prompts = informe, error, []

    def generate_json(self, prompt, schema, *, model, max_output_tokens, timeout_ms, purpose, system=None,
                      thinking_budget=None):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.informe


def informe(*argumentos):
    return AdvocateReport(arguments=list(argumentos))


class TestSoloBaja(unittest.TestCase):
    def setUp(self):
        self.items, self.etiquetas = grupo()
        self.juicio = judge_cluster(self.items, self.etiquetas, now=AHORA)
        self.assertEqual(self.juicio.verdict, "CONSTRUIR")
        self.ids = {i.id for i in self.items}

    def test_un_argumento_bloqueante_con_evidencia_real_baja(self):
        self.assertEqual(DOWNGRADE_SEVERITIES, frozenset({"bloqueante"}))
        resultado = apply_advocate(self.juicio, informe(AdvocateArgument(
            claim="Todos se quejan de lo mismo porque el proveedor ya lo arregló",
            evidence_ids=["hackernews:0", "stackexchange:1"], severity="bloqueante")), self.ids)
        self.assertEqual((resultado.verdict_before, resultado.verdict_after), ("CONSTRUIR", "INVESTIGAR MÁS"))
        self.assertTrue(resultado.downgraded)
        self.assertIn("bloqueante", presente(resultado.reason))

    def test_un_argumento_con_ids_inventados_se_descarta(self):
        resultado = apply_advocate(self.juicio, informe(AdvocateArgument(
            claim="Hay una herramienta gratuita que ya lo resuelve",
            evidence_ids=["hackernews:999"], severity="bloqueante")), self.ids)
        self.assertEqual(resultado.verdict_after, "CONSTRUIR")
        self.assertEqual(len(resultado.discarded), 1)
        self.assertEqual(resultado.arguments, [])

    def test_los_argumentos_menores_se_muestran_pero_no_bajan(self):
        resultado = apply_advocate(self.juicio, informe(AdvocateArgument(
            claim="La muestra es pequeña", evidence_ids=["github:2"], severity="importante")), self.ids)
        self.assertEqual((resultado.verdict_after, len(resultado.arguments)), ("CONSTRUIR", 1))

    def test_nunca_sube(self):
        items, etiquetas = grupo(parche=False)
        juicio = judge_cluster(items, etiquetas, now=AHORA)
        self.assertEqual(juicio.verdict, "INVESTIGAR MÁS")
        resultado = apply_advocate(juicio, informe(), {i.id for i in items})
        self.assertEqual(resultado.verdict_after, "INVESTIGAR MÁS")
        self.assertFalse(resultado.downgraded)


class TestEjecucion(unittest.TestCase):
    def setUp(self):
        self.items, self.etiquetas = grupo()
        self.juicio = judge_cluster(self.items, self.etiquetas, now=AHORA)

    def test_solo_se_llama_para_candidatos_a_construir(self):
        items, etiquetas = grupo(parche=False)
        llm = LLMAbogado(informe())
        resultado = run_advocate(judge_cluster(items, etiquetas, now=AHORA), items, provider=llm, model="m")
        self.assertEqual((llm.prompts, resultado.reason), ([], "not_applicable"))

    def test_el_prompt_lleva_la_evidencia_con_sus_ids(self):
        llm = LLMAbogado(informe())
        run_advocate(self.juicio, self.items, provider=llm, model="m")
        self.assertIn("hackernews:0", llm.prompts[0])
        self.assertIn("queja inventada 0", llm.prompts[0])

    def test_sin_proveedor_un_construir_sin_revisar_baja(self):
        resultado = run_advocate(self.juicio, self.items, provider=None, model=None)
        self.assertEqual((resultado.verdict_after, resultado.reason),
                         ("INVESTIGAR MÁS", "advocate_unavailable"))

    def test_un_error_del_llm_tambien_baja(self):
        llm = LLMAbogado(error=LLMError("fallo inventado"))
        resultado = run_advocate(self.juicio, self.items, provider=llm, model="m")
        self.assertEqual(resultado.verdict_after, "INVESTIGAR MÁS")
        self.assertTrue(presente(resultado.reason).startswith("advocate_unavailable"))


if __name__ == "__main__":
    unittest.main()
