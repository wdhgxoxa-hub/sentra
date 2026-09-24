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
from core.judge.coherencia import CoherenceGroup, CoherenceReport
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


def por_id(vectores):
    """Doble de vectores_frase: el vector de cada frase es el de su pieza."""
    return lambda frases: {i: vectores[i] for i in frases if i in vectores}


class LLMDoble:
    """Etiqueta cada ítem como dolor; el primero con parche y el segundo con pago."""

    def __init__(self):
        self.llamadas = {"etiquetas": 0, "abogado": 0}

    def generate_json(self, prompt, schema, *, model, max_output_tokens, timeout_ms, system=None,
                      thinking_budget=None):
        if schema is AdvocateReport:
            self.llamadas["abogado"] += 1
            return AdvocateReport()
        if schema is CoherenceReport:
            import json as _json

            self.llamadas["coherencia"] = self.llamadas.get("coherencia", 0) + 1
            return CoherenceReport(groups=[CoherenceGroup(group_id=g, same_problem=True, reason="mismo")
                                           for g in _json.loads(prompt[prompt.index("{"):])])
        self.llamadas["etiquetas"] += 1
        import json

        entrada = json.loads(prompt[prompt.index("["):])
        etiquetas = []
        for n, e in enumerate(entrada):
            etiquetas.append(LLMItemLabel(
                item_id=e["id"], is_pain=True, pain_confidence=0.9,
                intent="parche_casero" if n == 0 else "dispuesto_a_pagar" if n == 1 else "queja",
                workaround_described=n == 0, wtp_signal=n == 1, affected="author",
                evidence_spans={"is_pain": "I export every invoice by hand",
                                "affected": "I export every invoice by hand",
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
        resultado = run_judge(items, vectores, vectores_frase=por_id(vectores), provider=llm, model="m",
                              cache=InMemoryLabelCache(), now=AHORA)
        self.assertEqual(resultado.summary["items"], 11)
        self.assertEqual(resultado.summary["kept"], 10)
        self.assertEqual(resultado.summary["discarded"], {"too_short": 1})
        self.assertEqual(resultado.summary["clusters"], 1)
        [veredicto] = resultado.verdicts
        self.assertEqual(veredicto["verdict"], "CONSTRUIR")
        # G0 (coherencia) + G1–G8.
        self.assertEqual([g["gate"] for g in veredicto["gates"]], [f"G{n}" for n in range(9)])
        self.assertEqual(len(veredicto["member_ids"]), 10)
        self.assertFalse(veredicto["advocate"]["downgraded"])
        # Una llamada de coherencia por escaneo, con todos los grupos (G0).
        self.assertEqual(llm.llamadas, {"etiquetas": 1, "coherencia": 1, "abogado": 1})
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
        run_judge(items, vectores, vectores_frase=por_id(vectores), provider=llm, model="m", cache=InMemoryLabelCache(),
                  now=AHORA, label_batch_size=4)
        self.assertEqual(llm.llamadas["etiquetas"], 3, "10 ítems en lotes de 4")

    def test_el_tope_de_piezas_etiquetadas_se_puede_fijar(self):
        # Coste por escaneo (presupuesto de llamadas del usuario): lo que pasa
        # del tope queda undetermined con su motivo, sin llamada.
        items, vectores = escenario()
        llm = LLMDoble()
        resultado = run_judge(items, vectores, vectores_frase=por_id(vectores), provider=llm, model="m",
                              cache=InMemoryLabelCache(), now=AHORA, label_batch_size=4, label_max_items=4)
        self.assertEqual(llm.llamadas["etiquetas"], 1)
        self.assertEqual(resultado.summary["labeled"], 4)

    def test_con_tope_se_etiqueta_primero_el_tema_y_por_turnos_entre_fuentes(self):
        # Tras arreglar las fuentes, un escaneo trae ~800 piezas y se etiquetan 100:
        # en orden de llegada, la fuente más ruidosa se llevaba todo el cupo.
        from core.judge.pipeline import orden_de_etiquetado

        ruido = [pieza(n, texto=f"great video, thanks for sharing number {n}") for n in range(0, 9, 3)]
        # Una pieza del tema por fuente (FUENTES[n % 3]).
        tema = [pieza(n, texto=f"I export every invoice by hand, case {n}") for n in (1, 2, 9)]
        orden = orden_de_etiquetado(ruido + tema, ["invoice"])
        self.assertEqual({i.id for i in orden[:3]}, {i.id for i in tema}, "primero lo que nombra el tema")
        self.assertEqual(len({i.source for i in orden[:3]}), 3, "por turnos entre fuentes")
        self.assertEqual(len(orden), 6, "no se pierde nada")

    def test_con_tema_un_comentario_que_no_lo_nombra_no_se_etiqueta(self):
        # Escaneo de impagos: 41 de 82 «dolores» eran comentarios de YouTube sobre
        # el propio vídeo («la música está muy alta») y mezclaban los grupos.
        items, vectores = escenario()
        ruido = [pieza(n, texto=f"The background music is too loud, I cannot hear you, video {n}")
                 .model_copy(update={"kind": "comment"}) for n in (60, 61)]
        del_tema = pieza(62).model_copy(update={"kind": "comment"})  # QUEJA nombra «invoice»
        post_sin_tema = pieza(63, texto="The background music is too loud, I cannot hear you at all")
        resultado = run_judge([*items, *ruido, del_tema, post_sin_tema], vectores, vectores_frase=por_id(vectores),
                              provider=LLMDoble(), model="m", cache=InMemoryLabelCache(), now=AHORA,
                              tema=["invoice"])
        self.assertEqual(resultado.summary["discarded"], {"too_short": 1, "off_topic": 2})
        self.assertEqual(resultado.summary["kept"], 12, "el comentario del tema y el post siguen")

    def test_sin_tema_los_comentarios_no_se_filtran_por_tema(self):
        items, vectores = escenario()
        ruido = pieza(60, texto="The background music is too loud, I cannot hear you").model_copy(
            update={"kind": "comment"})
        resultado = run_judge([*items, ruido], vectores, vectores_frase=por_id(vectores), provider=LLMDoble(),
                              model="m", cache=InMemoryLabelCache(), now=AHORA)
        self.assertEqual(resultado.summary["discarded"], {"too_short": 1})

    def _juzgar_con_mezcla(self, confirma):
        """Un grupo de 10 que G0 ve mezclado con 4 frases del mismo problema; la
        segunda llamada confirma (o no) el subgrupo."""
        from core.judge.coherencia import CoherenceGroup, CoherenceReport

        items, vectores = escenario()

        class Doble(LLMDoble):
            def generate_json(self, prompt, schema, **kwargs):
                if schema is not CoherenceReport:
                    return super().generate_json(prompt, schema, **kwargs)
                import json as _json

                self.llamadas["coherencia"] = self.llamadas.get("coherencia", 0) + 1
                grupos = _json.loads(prompt[prompt.index("{"):])
                primera = self.llamadas["coherencia"] == 1
                return CoherenceReport(groups=[CoherenceGroup(
                    group_id=g, same_problem=not primera and confirma, reason="r",
                    dominant_ids=["f1", "f2", "f3", "f4"] if primera else [],
                    dominant_problem="impagos" if primera else "") for g in grupos])

        llm = Doble()
        resultado = run_judge(items, vectores, vectores_frase=por_id(vectores), provider=llm, model="m",
                              cache=InMemoryLabelCache(), now=AHORA)
        return resultado, llm

    def test_una_mezcla_con_problema_dominante_se_separa_y_se_confirma(self):
        resultado, llm = self._juzgar_con_mezcla(confirma=True)
        [veredicto] = resultado.verdicts
        esperados = sorted(pieza(n).id for n in range(10))[:4]
        self.assertEqual(veredicto["member_ids"], esperados, "solo las frases del problema dominante")
        g0 = veredicto["gates"][0]
        self.assertEqual((g0["gate"], g0["passed"]), ("G0", True))
        self.assertEqual(llm.llamadas["coherencia"], 2, "separar + confirmar")
        self.assertEqual(resultado.summary["split"], 1)

    def test_un_subgrupo_que_no_se_confirma_se_descarta(self):
        resultado, _ = self._juzgar_con_mezcla(confirma=False)
        [veredicto] = resultado.verdicts
        self.assertEqual((veredicto["verdict"], veredicto["rule"][:2], len(veredicto["member_ids"])),
                         ("DESCARTAR", "0:", 4))

    def test_honestidad_con_datos_demo_nunca_construir(self):
        items, vectores = escenario(procedencia="demo")
        resultado = run_judge(items, vectores, vectores_frase=por_id(vectores), provider=LLMDoble(), model="m",
                              cache=InMemoryLabelCache(), now=AHORA)
        self.assertNotIn("CONSTRUIR", [v["verdict"] for v in resultado.verdicts])

    def test_sin_proveedor_todo_undetermined_y_ningun_nicho(self):
        """Sin etiquetas no hay dolor verificado, y sin dolor no hay nichos
        (AUD2-001: antes salía un DESCARTAR hecho de ítems sin determinar)."""
        items, vectores = escenario()
        resultado = run_judge(items, vectores, vectores_frase=por_id(vectores), provider=None, model=None,
                              cache=InMemoryLabelCache(), now=AHORA)
        self.assertEqual(resultado.summary["undetermined"], {"no_provider": 10})
        self.assertEqual((resultado.summary["pain"], resultado.verdicts), (0, []))

    def test_sin_vectores_no_hay_grupos_y_se_dice(self):
        items, _ = escenario()
        resultado = run_judge(items, {}, vectores_frase=por_id({}), provider=LLMDoble(), model="m",
                              cache=InMemoryLabelCache(), now=AHORA)
        self.assertEqual((resultado.summary["clusters"], resultado.verdicts), (0, []))


if __name__ == "__main__":
    unittest.main()
