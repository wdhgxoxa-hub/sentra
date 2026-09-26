"""
El etiquetador conoce el tema del escaneo (Fase 3, medida A de Walter)
======================================================================

Escaneo 2: 0 de 53 quejas eran del tema. El etiquetador no lo conocía y
`is_pain` decía «hay un problema», no «hay un problema de ESTE tema»; su
caché (por texto) reutilizaba la etiqueta en cualquier escaneo.

labels-v5: con tema, cada etiqueta dice si es del tema (`del_tema`, con su
fragmento literal, como las demás). Solo cuenta como queja la que es del
tema. La caché va por pieza + tema: nunca se reutiliza entre temas. Mismas
llamadas a Gemini: los lotes no cambian.
"""

import json
import unittest
from datetime import UTC, datetime
from typing import Any

from core.evidence.model import EvidenceItem
from core.judge.dimensions import pain_items
from core.judge.labels import (
    LABELER_VERSION,
    SYSTEM_PROMPT_TEMA,
    InMemoryLabelCache,
    LLMItemLabel,
    LLMLabelBatch,
    TemaDelEscaneo,
    etiquetador,
    label_items,
    verify_label,
)

AHORA = datetime(2026, 9, 25, tzinfo=UTC)
TEMA = TemaDelEscaneo(descripcion="Perseguir a los clientes para que manden sus documentos al contable",
                      palabras=("documentos contabilidad", "chase client documents"))
DEL_TEMA = "Every month I chase my clients for their receipts and bank statements"
AJENO = "My Typesense filter_by returns zero results and I am stuck with the query"


def pieza(n: int, texto: str) -> EvidenceItem:
    return EvidenceItem(id=f"hackernews:{n}", source="hackernews", community="c", kind="post", text=texto,
                        url=f"https://example.com/{n}", author_hash=f"{n:064x}", created_at=AHORA,
                        fetched_at=AHORA, data_source="real")


class Doble:
    """Etiqueta como dolor todo lo que recibe; del tema, solo lo que habla de clientes."""

    def __init__(self) -> None:
        self.llamadas: list[dict[str, object]] = []

    def generate_json(self, prompt, schema, *, model, max_output_tokens, timeout_ms, purpose, system=None,
                      thinking_budget=None):
        assert schema is LLMLabelBatch
        self.llamadas.append({"prompt": prompt, "system": system})
        entrada = json.loads(prompt[prompt.index("\n[") + 1:])
        etiquetas = []
        for e in entrada:
            del_tema = "clients" in e["text"]
            spans = {"is_pain": e["text"][:20], "affected": e["text"][:20], "intent": e["text"][:20]}
            if del_tema:
                spans["del_tema"] = e["text"][:30]
            etiquetas.append(LLMItemLabel(
                item_id=e["id"], is_pain=True, pain_confidence=0.9, intent="queja", workaround_described=False,
                wtp_signal=False, affected="author", del_tema=del_tema, evidence_spans=spans))
        return LLMLabelBatch(labels=etiquetas)


class TestClaveDeCache(unittest.TestCase):
    def test_labels_v5(self):
        self.assertEqual(LABELER_VERSION, "labels-v5")

    def test_la_clave_lleva_el_tema_y_distingue_temas(self):
        otro = TemaDelEscaneo(descripcion="Convertir un PDF a Word", palabras=("pdf a word",))
        self.assertEqual(etiquetador("m", None), "labels-v5/m")
        self.assertTrue(etiquetador("m", TEMA).startswith("labels-v5/m/tema-"))
        self.assertNotEqual(etiquetador("m", TEMA), etiquetador("m", otro))
        # El orden de las palabras y los espacios no cambian el tema.
        igual = TemaDelEscaneo(descripcion="  Perseguir a los clientes para que manden sus documentos al contable ",
                               palabras=("chase client documents", "documentos contabilidad"))
        self.assertEqual(etiquetador("m", TEMA), etiquetador("m", igual))

    def test_nunca_se_reutiliza_una_etiqueta_entre_temas(self):
        cache, doble = InMemoryLabelCache(), Doble()
        items = [pieza(1, DEL_TEMA)]
        label_items(items, provider=doble, model="m", cache=cache, tema=TEMA)
        label_items(items, provider=doble, model="m", cache=cache, tema=TEMA)
        self.assertEqual(len(doble.llamadas), 1, "mismo tema: de la caché")
        label_items(items, provider=doble, model="m", cache=cache,
                    tema=TemaDelEscaneo(descripcion="Otro tema", palabras=("otro",)))
        self.assertEqual(len(doble.llamadas), 2, "otro tema: se etiqueta otra vez")


class TestMismasLlamadas(unittest.TestCase):
    def test_con_y_sin_tema_salen_las_mismas_llamadas(self):
        items = [pieza(n, f"{DEL_TEMA} número {n}") for n in range(45)]
        sin, con = Doble(), Doble()
        label_items(items, provider=sin, model="m", cache=InMemoryLabelCache(), batch_size=20)
        label_items(items, provider=con, model="m", cache=InMemoryLabelCache(), batch_size=20, tema=TEMA)
        self.assertEqual(len(sin.llamadas), 3)
        self.assertEqual(len(con.llamadas), len(sin.llamadas))

    def test_el_tema_va_en_el_prompt_y_sus_reglas_en_el_sistema(self):
        doble = Doble()
        label_items([pieza(1, DEL_TEMA)], provider=doble, model="m", cache=InMemoryLabelCache(), tema=TEMA)
        prompt, sistema = str(doble.llamadas[0]["prompt"]), str(doble.llamadas[0]["system"])
        self.assertIn(TEMA.descripcion, prompt)
        self.assertIn("chase client documents", prompt)
        self.assertIn(SYSTEM_PROMPT_TEMA, sistema)

    def test_sin_tema_no_se_habla_de_tema(self):
        doble = Doble()
        label_items([pieza(1, DEL_TEMA)], provider=doble, model="m", cache=InMemoryLabelCache())
        self.assertNotIn(SYSTEM_PROMPT_TEMA, str(doble.llamadas[0]["system"]))


class TestVerificacionDelTema(unittest.TestCase):
    def etiqueta(self, **cambios: Any) -> LLMItemLabel:
        base: dict[str, Any] = {"item_id": "x", "is_pain": True, "pain_confidence": 0.8, "intent": "queja",
                "workaround_described": False, "wtp_signal": False, "affected": "author",
                "evidence_spans": {"is_pain": "chase my clients", "intent": "chase my clients",
                                   "affected": "I chase my clients", "del_tema": "chase my clients for their receipts"}}
        base.update(cambios)
        return LLMItemLabel(**base)

    def test_del_tema_con_fragmento_literal(self):
        self.assertEqual(verify_label(self.etiqueta(del_tema=True), DEL_TEMA, con_tema=True).del_tema, "yes")

    def test_del_tema_sin_fragmento_literal_no_se_sabe(self):
        inventada = self.etiqueta(del_tema=True, evidence_spans={"is_pain": "chase my clients",
                                                                 "affected": "I chase my clients",
                                                                 "del_tema": "chasing documents for the accountant"})
        self.assertEqual(verify_label(inventada, DEL_TEMA, con_tema=True).del_tema, "undetermined")

    def test_fuera_del_tema(self):
        self.assertEqual(verify_label(self.etiqueta(del_tema=False), DEL_TEMA, con_tema=True).del_tema, "no")

    def test_con_tema_y_sin_respuesta_no_se_sabe(self):
        self.assertEqual(verify_label(self.etiqueta(del_tema=None), DEL_TEMA, con_tema=True).del_tema,
                         "undetermined")

    def test_sin_tema_no_hay_campo(self):
        self.assertIsNone(verify_label(self.etiqueta(del_tema=None), DEL_TEMA).del_tema)


class TestSoloCuentaLoDelTema(unittest.TestCase):
    def test_una_queja_ajena_no_cuenta(self):
        items = [pieza(1, DEL_TEMA), pieza(2, AJENO)]
        etiquetas = label_items(items, provider=Doble(), model="m", cache=InMemoryLabelCache(), tema=TEMA)
        self.assertEqual(etiquetas["hackernews:2"].is_pain, "yes", "es una queja…")
        self.assertEqual(etiquetas["hackernews:2"].del_tema, "no", "…pero no de este tema")
        self.assertEqual([i.id for i in pain_items(items, etiquetas)], ["hackernews:1"])

    def test_sin_tema_cuenta_toda_queja(self):
        items = [pieza(1, DEL_TEMA), pieza(2, AJENO)]
        etiquetas = label_items(items, provider=Doble(), model="m", cache=InMemoryLabelCache())
        self.assertEqual(len(pain_items(items, etiquetas)), 2)


if __name__ == "__main__":
    unittest.main()


class TestElJuezConTema(unittest.TestCase):
    def test_solo_las_quejas_del_tema_forman_grupos_y_el_resumen_cuenta_las_ajenas(self):
        from core.judge.advocate import AdvocateReport
        from core.judge.coherencia import CoherenceGroup, CoherenceReport
        from core.judge.pipeline import run_judge

        class DobleCompleto(Doble):
            def generate_json(self, prompt, schema, **kwargs):
                if schema is AdvocateReport:
                    return AdvocateReport()
                if schema is CoherenceReport:
                    return CoherenceReport(groups=[CoherenceGroup(group_id=g, same_problem=True, reason="mismo")
                                                   for g in json.loads(prompt[prompt.index("{"):])])
                return super().generate_json(prompt, schema, **kwargs)

        del_tema = [pieza(n, f"{DEL_TEMA} (caso {n})") for n in range(5)]
        ajenas = [pieza(n, f"{AJENO} (caso {n})") for n in range(5, 10)]
        items = del_tema + ajenas
        vectores = {i.id: [1.0, 0.01 * n, 0.0] for n, i in enumerate(items)}
        resultado = run_judge(items, vectores, provider=DobleCompleto(), model="m", cache=InMemoryLabelCache(),
                              now=AHORA, vectores_frase=lambda f: {i: vectores[i] for i in f},
                              tema=list(TEMA.palabras), descripcion=TEMA.descripcion)
        self.assertEqual(resultado.summary["pain"], 5)
        self.assertEqual(resultado.summary["pain_off_topic"], 5)
        miembros = {m for v in resultado.verdicts for m in v["member_ids"]}
        self.assertEqual(miembros, {i.id for i in del_tema})
        self.assertTrue(all(v["labeler_version"] == etiquetador("m", TEMA) for v in resultado.verdicts))
