"""
Juez completo: calidad -> etiquetado -> agrupación -> compuertas -> abogado
===========================================================================

El orquestador une las etapas y devuelve los veredictos listos para guardar
y un resumen con cifras (descartes por motivo, undetermined por motivo,
grupos, veredictos). Dobles del LLM y vectores hechos a mano; textos
inventados.
"""

import unittest
from datetime import UTC, datetime, timedelta

from core.evidence.model import EvidenceItem
from core.judge.advocate import AdvocateReport
from core.judge.labels import InMemoryLabelCache, LLMItemLabel, LLMLabelBatch
from core.judge.pipeline import run_judge

AHORA = datetime(2026, 9, 1, tzinfo=UTC)
FUENTES = ("hackernews", "stackexchange", "github")
QUEJA = "I export every invoice by hand into a spreadsheet and it takes hours"


def pieza(n, texto=None, procedencia="real"):
    fuente = FUENTES[n % 3]
    return EvidenceItem(id=f"{fuente}:{n}", source=fuente, community="c", kind="post",
                        text=texto or f"{QUEJA} (caso {n})", url=f"https://example.com/{n}",
                        author_hash=f"{n:064x}", created_at=AHORA - timedelta(days=5),
                        fetched_at=AHORA, thread_id=f"{fuente}:{n}", language="en",
                        data_source=procedencia)


class LLMDoble:
    """Etiqueta cada ítem como dolor; el primero con parche y el segundo con pago."""

    def __init__(self):
        self.llamadas = {"etiquetas": 0, "abogado": 0}

    def generate_json(self, prompt, schema, *, model, max_output_tokens, timeout_ms, system=None,
                      thinking_budget=None):
        if schema is AdvocateReport:
            self.llamadas["abogado"] += 1
            return AdvocateReport()
        self.llamadas["etiquetas"] += 1
        import json

        entrada = json.loads(prompt[prompt.index("["):])
        etiquetas = []
        for n, e in enumerate(entrada):
            etiquetas.append(LLMItemLabel(
                item_id=e["id"], is_pain=True, pain_confidence=0.9,
                intent="parche_casero" if n == 0 else "dispuesto_a_pagar" if n == 1 else "queja",
                workaround_described=n == 0, wtp_signal=n == 1,
                evidence_spans={"is_pain": "I export every invoice by hand",
                                "intent": "I export every invoice by hand",
                                "workaround_described": "into a spreadsheet",
                                "wtp_signal": "I export every invoice"}))
        return LLMLabelBatch(labels=etiquetas)


def escenario(procedencia="real"):
    items = [pieza(n, procedencia=procedencia) for n in range(10)]
    items.append(pieza(50, texto="+1"))  # lo tira el filtro de calidad
    vectores = {i.id: [1.0, 0.01 * n, 0.0] for n, i in enumerate(items)}
    return items, vectores


class TestJuezCompleto(unittest.TestCase):
    def test_de_extremo_a_extremo_con_dobles(self):
        items, vectores = escenario()
        llm = LLMDoble()
        resultado = run_judge(items, vectores, provider=llm, model="m",
                              cache=InMemoryLabelCache(), now=AHORA)
        self.assertEqual(resultado.summary["items"], 11)
        self.assertEqual(resultado.summary["kept"], 10)
        self.assertEqual(resultado.summary["discarded"], {"too_short": 1})
        self.assertEqual(resultado.summary["clusters"], 1)
        [veredicto] = resultado.verdicts
        self.assertEqual(veredicto["verdict"], "CONSTRUIR")
        self.assertEqual(len(veredicto["gates"]), 8)
        self.assertEqual(len(veredicto["member_ids"]), 10)
        self.assertFalse(veredicto["advocate"]["downgraded"])
        self.assertEqual(llm.llamadas, {"etiquetas": 1, "abogado": 1})
        self.assertEqual(resultado.summary["verdicts"], {"CONSTRUIR": 1})
        # B4: cada veredicto sabe con qué versiones se produjo.
        from core.judge.clustering import CLUSTERING_VERSION
        from core.judge.dimensions import WEIGHTS_VERSION
        from core.judge.labels import LABELER_VERSION

        self.assertEqual((veredicto["labeler_version"], veredicto["clustering_version"],
                          veredicto["weights_version"]),
                         (f"{LABELER_VERSION}/m", CLUSTERING_VERSION, WEIGHTS_VERSION))

    def test_el_tamano_de_lote_del_etiquetado_se_puede_fijar(self):
        # El cupo de llamadas manda: lotes mayores, menos llamadas.
        items, vectores = escenario()
        llm = LLMDoble()
        run_judge(items, vectores, provider=llm, model="m", cache=InMemoryLabelCache(),
                  now=AHORA, label_batch_size=4)
        self.assertEqual(llm.llamadas["etiquetas"], 3, "10 ítems en lotes de 4")

    def test_honestidad_con_datos_demo_nunca_construir(self):
        items, vectores = escenario(procedencia="demo")
        resultado = run_judge(items, vectores, provider=LLMDoble(), model="m",
                              cache=InMemoryLabelCache(), now=AHORA)
        self.assertNotIn("CONSTRUIR", [v["verdict"] for v in resultado.verdicts])

    def test_sin_proveedor_todo_undetermined_y_ningun_construir(self):
        items, vectores = escenario()
        resultado = run_judge(items, vectores, provider=None, model=None,
                              cache=InMemoryLabelCache(), now=AHORA)
        self.assertEqual(resultado.summary["undetermined"], {"no_provider": 10})
        self.assertEqual([v["verdict"] for v in resultado.verdicts], ["DESCARTAR"])

    def test_sin_vectores_no_hay_grupos_y_se_dice(self):
        items, _ = escenario()
        resultado = run_judge(items, {}, provider=LLMDoble(), model="m",
                              cache=InMemoryLabelCache(), now=AHORA)
        self.assertEqual((resultado.summary["clusters"], resultado.verdicts), (0, []))


if __name__ == "__main__":
    unittest.main()
