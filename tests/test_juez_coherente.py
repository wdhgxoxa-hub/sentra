"""
El juez agrupa problemas, no temas (AUD2-001, 6.3)
=================================================

Se agrupaba todo lo que pasaba el filtro de calidad: los grupos salían por
tema («email») y mezclaban lanzamientos y comentarios sueltos. Ahora:
- solo la evidencia con dolor pertinente forma nichos (un lanzamiento no,
  aunque el LLM lo etiquete como dolor, que es justo el error real);
- lo demás que queda cerca del grupo solo sirve de contexto para G7
  (quién habla bien de un competidor gratuito);
- G2 (autores distintos) escala con el tamaño del escaneo: 8 fijos era
  inalcanzable con ~100 piezas;
- los términos del tema del escaneo no nombran los nichos.
"""

import json
import unittest

from core.judge.advocate import AdvocateReport
from core.judge.clustering import CLUSTERING_VERSION
from core.judge.coherencia import CoherenceGroup, CoherenceReport
from core.judge.dimensions import WEIGHTS_VERSION
from core.judge.gates import MIN_DISTINCT_AUTHORS, umbral_autores
from core.judge.labels import (
    CompetitorMention,
    InMemoryLabelCache,
    LLMItemLabel,
    LLMLabelBatch,
)
from core.judge.pipeline import run_judge
from tests.test_judge_pipeline import AHORA, pieza


class DobleQueSeEquivoca:
    """Etiqueta como dolor con parche TODO, lanzamientos incluidos (el error real);
    el ítem «opinion» no es dolor y habla bien de un competidor gratuito."""

    def generate_json(self, prompt, schema, *, model, max_output_tokens, timeout_ms, purpose, system=None,
                      thinking_budget=None):
        if schema is AdvocateReport:
            return AdvocateReport()
        if schema is CoherenceReport:
            return CoherenceReport(groups=[CoherenceGroup(group_id=g, same_problem=True, reason="mismo")
                                           for g in json.loads(prompt[prompt.index("{"):])])
        etiquetas = []
        for e in json.loads(prompt[prompt.index("["):]):
            if "TallyBird" in e["text"]:
                etiquetas.append(LLMItemLabel(
                    item_id=e["id"], is_pain=False, pain_confidence=0.9, intent="mencion_competidor",
                    workaround_described=False, wtp_signal=False, affected="none",
                    competitors_mentioned=[CompetitorMention(name="TallyBird", stance="satisfecho", free=True,
                                                             evidence_span="TallyBird")],
                    evidence_spans={"intent": "TallyBird"}))
                continue
            span = e["text"][:20]
            etiquetas.append(LLMItemLabel(
                item_id=e["id"], is_pain=True, pain_confidence=0.9, intent="parche_casero",
                workaround_described=True, wtp_signal=False, affected="author", del_tema=True,
                evidence_spans={"is_pain": span, "intent": span, "workaround_described": span,
                                "affected": span, "del_tema": span}))
        return LLMLabelBatch(labels=etiquetas)


def lanzamiento(n):
    return pieza(n, texto=f"I built an invoice exporter, try it (build {n})").model_copy(
        update={"title": f"Show HN: Invoicer {n}"})


def por_id(vectores):
    """Doble de vectores_frase: el vector de cada frase es el de su pieza."""
    return lambda frases: {i: vectores[i] for i in frases if i in vectores}


def juzgar(items, vectores, **extra):
    extra.setdefault("vectores_frase", por_id(vectores))
    extra.setdefault("provider", DobleQueSeEquivoca())
    return run_judge(items, vectores, model="m", cache=InMemoryLabelCache(), now=AHORA, **extra)


class TestJuezCoherente(unittest.TestCase):
    def test_los_lanzamientos_no_forman_nichos_aunque_el_llm_diga_que_son_dolor(self):
        quejas = [pieza(n) for n in range(6)]
        lanzamientos = [lanzamiento(n) for n in range(10, 14)]
        vectores = {i.id: [1.0, 0.01 * k, 0.0] for k, i in enumerate(quejas + lanzamientos)}
        resultado = juzgar(quejas + lanzamientos, vectores)
        miembros = {m for v in resultado.verdicts for m in v["member_ids"]}
        self.assertEqual(miembros, {i.id for i in quejas})
        self.assertEqual(resultado.summary["launches_excluded"], 4)

    def test_g2_escala_con_el_escaneo(self):
        self.assertEqual(umbral_autores(0), 3)
        self.assertEqual(umbral_autores(10), 3)
        self.assertEqual(umbral_autores(41), 5)
        self.assertEqual(umbral_autores(10_000), MIN_DISTINCT_AUTHORS)

    def test_g2_del_escaneo_llega_a_las_compuertas(self):
        quejas = [pieza(n) for n in range(6)]
        vectores = {i.id: [1.0, 0.01 * k, 0.0] for k, i in enumerate(quejas)}
        [veredicto] = juzgar(quejas, vectores).verdicts
        g2 = next(g for g in veredicto["gates"] if g["gate"] == "G2")
        self.assertEqual(g2["threshold"], 3)
        self.assertTrue(g2["passed"], "6 autores distintos con umbral 3")

    def test_la_evidencia_cercana_sin_dolor_informa_a_g7(self):
        quejas = [pieza(n) for n in range(6)]
        opiniones = [pieza(n, texto=f"TallyBird does this for free and works great ({n})") for n in (20, 21, 22)]
        lejos = pieza(30, texto="TallyBird is fine for something else entirely")
        vectores = {i.id: [1.0, 0.01 * k, 0.0] for k, i in enumerate(quejas + opiniones)}
        vectores[lejos.id] = [0.0, 0.0, 1.0]
        [veredicto] = juzgar(quejas + opiniones + [lejos], vectores).verdicts
        g7 = next(g for g in veredicto["gates"] if g["gate"] == "G7")
        self.assertFalse(g7["passed"])
        self.assertTrue(g7["measured"])
        self.assertNotIn(lejos.id, g7["evidence_ids"])
        self.assertEqual(veredicto["verdict"], "DESCARTAR")

    def test_la_dimension_de_competencia_ve_la_misma_evidencia_que_g7(self):
        # En la release, G7 salía medida con el contexto y la dimensión «hueco»
        # decía «sin datos de competencia» en el mismo veredicto.
        quejas = [pieza(n) for n in range(6)]
        opiniones = [pieza(n, texto=f"TallyBird does this for free and works great ({n})") for n in (20, 21, 22)]
        lejos = pieza(30, texto="TallyBird is fine for something else entirely")
        vectores = {i.id: [1.0, 0.01 * k, 0.0] for k, i in enumerate(quejas + opiniones)}
        vectores[lejos.id] = [0.0, 0.0, 1.0]
        [veredicto] = juzgar(quejas + opiniones + [lejos], vectores).verdicts
        g7 = next(g for g in veredicto["gates"] if g["gate"] == "G7")
        hueco = next(d for d in veredicto["dimensions"] if d["name"] == "hueco")
        self.assertNotEqual(hueco["note"], "sin_datos")
        self.assertEqual(set(hueco["item_ids"]), set(g7["evidence_ids"]))

    def test_el_tema_del_escaneo_no_nombra_los_nichos(self):
        quejas = [pieza(n) for n in range(6)]
        vectores = {i.id: [1.0, 0.01 * k, 0.0] for k, i in enumerate(quejas)}
        [veredicto] = juzgar(quejas, vectores, tema=["invoice", "Export"]).verdicts
        self.assertFalse({"invoice", "export"} & set(veredicto["keywords"]))

    def test_se_agrupa_por_la_frase_del_problema_y_no_por_el_post_entero(self):
        # clustering-v5: posts del mismo tema se parecen enteros (saludo, stack,
        # código); lo que distingue el problema es la frase verificada.
        quejas = [pieza(n) for n in range(6)]
        mismo_post = {i.id: [1.0, 0.0, 0.0] for i in quejas}
        frases = {i.id: ([1.0, 0.0, 0.0] if n < 3 else [0.0, 1.0, 0.0]) for n, i in enumerate(quejas)}
        resultado = juzgar(quejas, mismo_post, vectores_frase=lambda f: {k: frases[k] for k in f})
        self.assertEqual(sorted(sorted(v["member_ids"]) for v in resultado.verdicts),
                         [sorted(i.id for i in quejas[:3]), sorted(i.id for i in quejas[3:])])

    def test_las_frases_que_se_vectorizan_son_las_verificadas(self):
        quejas = [pieza(n) for n in range(4)]
        vectores = {i.id: [1.0, 0.01 * k, 0.0] for k, i in enumerate(quejas)}
        vistas: dict[str, str] = {}

        def espia(frases):
            vistas.update(frases)
            return {i: vectores[i] for i in frases}

        juzgar(quejas, vectores, vectores_frase=espia)
        # DobleQueSeEquivoca cita como prueba de affected los primeros 20 caracteres.
        self.assertEqual(vistas, {i.id: i.text[:20] for i in quejas})

    def test_la_frase_que_se_agrupa_es_la_del_problema_no_la_de_quien(self):
        # clustering-v6: con real data, el fragmento de affected solía ser la
        # presentación («I'm building an app…») y juntaba a 20 autores distintos.
        # El problema está en el fragmento de is_pain.
        from core.judge.labels import VerifiedLabel
        from core.judge.pipeline import frase_del_problema

        etiqueta = VerifiedLabel(item_id="x", content_hash="h", labeler="l", is_pain="yes",
                                 intent="queja", workaround_described="no", wtp_signal="no",
                                 affected="author",
                                 evidence_spans={"is_pain": "the emails land in spam",
                                                 "affected": "I am building a SaaS"})
        self.assertEqual(frase_del_problema(etiqueta), "the emails land in spam")

    def test_versiones_nuevas(self):
        self.assertEqual(CLUSTERING_VERSION, "clustering-v10")
        self.assertEqual(WEIGHTS_VERSION, "judge-weights-v6")


if __name__ == "__main__":
    unittest.main()
