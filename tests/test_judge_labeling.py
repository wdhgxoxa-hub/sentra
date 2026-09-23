"""
Juez, etapa 1: etiquetado con verificación anti-alucinación
===========================================================

Dobles del LLM construidos desde el conjunto dorado. Se prueba que:
- una etiqueta positiva sin fragmento literal queda `undetermined`
  (test obligatorio de la misión);
- sin proveedor todo queda `undetermined`, nunca una heurística;
- el mismo texto no se etiqueta dos veces (caché por hash de contenido);
- se procesa por lotes y se respetan los presupuestos (tokens e ítems);
- la concordancia con el conjunto dorado se mide igual con dobles que con
  el modelo real.
"""

import json
import unittest
from datetime import UTC, datetime
from pathlib import Path

from core.evidence.model import EvidenceItem
from core.judge.calibration import agreement
from core.judge.labels import (
    LABELER_VERSION,
    InMemoryLabelCache,
    LLMItemLabel,
    LLMLabelBatch,
    label_items,
    verify_label,
)
from core.llm.base import LLMBudgetExhausted

AHORA = datetime(2026, 9, 1, tzinfo=UTC)
GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "golden_labels.json")
                    .read_text(encoding="utf-8"))["items"]


def item_de(dorado, prefijo="hackernews"):
    return EvidenceItem(id=f"{prefijo}:{dorado['id']}", source=prefijo, community="c", kind="post",
                        text=dorado["text"], url="https://example.com/x", author_hash=None,
                        created_at=AHORA, fetched_at=AHORA, language=dorado["lang"],
                        data_source="real")


def etiqueta_perfecta(item_id, dorado):
    esperado, spans = dorado["expected"], dorado["spans"]
    return LLMItemLabel(
        item_id=item_id, is_pain=esperado["is_pain"], pain_confidence=0.9,
        intent=esperado["intent"], workaround_described=esperado["workaround_described"],
        wtp_signal=esperado["wtp_signal"],
        competitors_mentioned=[{"name": c["name"], "stance": c["stance"],
                                "evidence_span": spans[f"competitors.{c['name']}"]}
                               for c in esperado["competitors"]],
        evidence_spans={k: v for k, v in spans.items() if not k.startswith("competitors.")})


class LLMDoble:
    """Responde a cada lote con las etiquetas del conjunto dorado (o las que se le digan)."""

    def __init__(self, por_texto=None, falla_en_lote=None, omite=()):
        self.por_texto = por_texto or {d["text"]: d for d in GOLDEN}
        self.lotes = []
        self.falla_en_lote = falla_en_lote
        self.omite = set(omite)
        self.presupuestos = []

    def generate_json(self, prompt, schema, *, model, max_output_tokens, timeout_ms, system=None,
                      thinking_budget=None):
        assert schema is LLMLabelBatch
        self.presupuestos.append(thinking_budget)
        entrada = json.loads(prompt[prompt.index("["):])
        self.lotes.append([e["id"] for e in entrada])
        if self.falla_en_lote is not None and len(self.lotes) == self.falla_en_lote:
            raise LLMBudgetExhausted("presupuesto agotado")
        etiquetas = [etiqueta_perfecta(e["id"], self.por_texto[e["text"]])
                     for e in entrada if e["id"] not in self.omite]
        return LLMLabelBatch(labels=etiquetas)


class TestVerificacion(unittest.TestCase):
    TEXTO = "I wrote a Python script that scrapes our CRM export and emails the weekly report."

    def etiqueta(self, **cambios):
        base = {"item_id": "x", "is_pain": True, "pain_confidence": 0.8, "intent": "parche_casero",
                "workaround_described": True, "wtp_signal": False,
                "evidence_spans": {"is_pain": "scrapes our CRM export",
                                   "intent": "I wrote a Python script",
                                   "workaround_described": "I wrote a Python script"}}
        base.update(cambios)
        return LLMItemLabel(**base)

    def test_con_fragmentos_literales_queda_verificada(self):
        verificada = verify_label(self.etiqueta(), self.TEXTO)
        self.assertEqual((verificada.is_pain, verificada.intent, verificada.workaround_described,
                          verificada.wtp_signal), ("yes", "parche_casero", "yes", "no"))

    def test_un_fragmento_inventado_anula_la_etiqueta(self):
        # Obligatorio en la misión: el LLM «cita» algo que el texto no dice.
        inventada = self.etiqueta(evidence_spans={
            "is_pain": "this is costing us thousands every month",
            "intent": "I wrote a Python script",
            "workaround_described": "we hired an intern to do it"})
        verificada = verify_label(inventada, self.TEXTO)
        self.assertEqual(verificada.is_pain, "undetermined")
        self.assertEqual(verificada.workaround_described, "undetermined")
        self.assertEqual(verificada.intent, "parche_casero", "la que sí es literal se conserva")

    def test_sin_fragmento_tambien_queda_undetermined(self):
        verificada = verify_label(self.etiqueta(wtp_signal=True), self.TEXTO)
        self.assertEqual(verificada.wtp_signal, "undetermined")

    def test_un_competidor_sin_fragmento_literal_no_cuenta(self):
        verificada = verify_label(self.etiqueta(competitors_mentioned=[
            {"name": "LedgerLoop", "stance": "queja", "evidence_span": "LedgerLoop is awful"}]), self.TEXTO)
        self.assertEqual(verificada.competitors, [])

    def test_una_pregunta_neutra_no_necesita_fragmento(self):
        neutra = self.etiqueta(is_pain=False, intent="pregunta_neutra", workaround_described=False,
                               evidence_spans={})
        verificada = verify_label(neutra, self.TEXTO)
        self.assertEqual((verificada.is_pain, verificada.intent), ("no", "pregunta_neutra"))


class TestInstrucciones(unittest.TestCase):
    """Concordancia real v1: 8 intents quedaron undetermined porque el prompt
    no decía con qué claves rellenar evidence_spans."""

    def test_el_prompt_y_el_esquema_nombran_las_claves_de_los_fragmentos(self):
        from core.judge.labels import SPAN_KEYS, SYSTEM_PROMPT

        self.assertEqual(SPAN_KEYS, ("is_pain", "intent", "workaround_described", "wtp_signal"))
        descripcion = LLMItemLabel.model_json_schema()["properties"]["evidence_spans"]["description"]
        for clave in SPAN_KEYS:
            self.assertIn(clave, SYSTEM_PROMPT)
            self.assertIn(clave, descripcion)

    def test_la_version_cambia_con_el_prompt(self):
        self.assertEqual(LABELER_VERSION, "labels-v2")


class TestEtiquetado(unittest.TestCase):
    def test_sin_proveedor_todo_undetermined_sin_heuristicas(self):
        items = [item_de(d) for d in GOLDEN[:5]]
        etiquetas = label_items(items, provider=None, model=None, cache=InMemoryLabelCache())
        for etiqueta in etiquetas.values():
            self.assertEqual((etiqueta.is_pain, etiqueta.intent, etiqueta.workaround_described,
                              etiqueta.wtp_signal), ("undetermined",) * 4)
            self.assertEqual(etiqueta.undetermined_reason, "no_provider")

    def test_por_lotes(self):
        doble = LLMDoble()
        items = [item_de(d) for d in GOLDEN[:45]]
        label_items(items, provider=doble, model="m", cache=InMemoryLabelCache(), batch_size=20)
        self.assertEqual([len(lote) for lote in doble.lotes], [20, 20, 5])

    def test_el_mismo_texto_no_se_etiqueta_dos_veces(self):
        doble, cache = LLMDoble(), InMemoryLabelCache()
        uno = item_de(GOLDEN[0], "hackernews")
        otro = item_de(GOLDEN[0], "stackexchange")  # crosspost: mismo texto, otra fuente
        etiquetas = label_items([uno, otro], provider=doble, model="m", cache=cache)
        self.assertEqual(sum(len(lote) for lote in doble.lotes), 1)
        self.assertEqual(etiquetas[otro.id].is_pain, "yes")
        label_items([uno], provider=doble, model="m", cache=cache)
        self.assertEqual(sum(len(lote) for lote in doble.lotes), 1, "la caché sobrevive entre llamadas")

    def test_presupuesto_de_tokens_agotado(self):
        doble = LLMDoble(falla_en_lote=2)
        items = [item_de(d) for d in GOLDEN[:30]]
        etiquetas = label_items(items, provider=doble, model="m", cache=InMemoryLabelCache(), batch_size=10)
        razones = [etiquetas[i.id].undetermined_reason for i in items]
        self.assertEqual(razones[:10], [None] * 10)
        self.assertEqual(set(razones[10:]), {"llm_budget_exhausted"})
        self.assertEqual(len(doble.lotes), 2, "tras agotarse no se pide más")

    def test_tope_de_items_por_escaneo(self):
        items = [item_de(d) for d in GOLDEN[:15]]
        etiquetas = label_items(items, provider=LLMDoble(), model="m", cache=InMemoryLabelCache(),
                                max_items=10)
        razones = [etiquetas[i.id].undetermined_reason for i in items]
        self.assertEqual(razones.count("item_budget"), 5)

    def test_un_item_que_el_llm_omite_queda_undetermined(self):
        items = [item_de(d) for d in GOLDEN[:3]]
        etiquetas = label_items(items, provider=LLMDoble(omite={items[1].id}), model="m",
                                cache=InMemoryLabelCache())
        self.assertEqual(etiquetas[items[1].id].undetermined_reason, "missing_in_response")

    def test_la_version_del_etiquetador_queda_registrada(self):
        [etiqueta] = label_items([item_de(GOLDEN[0])], provider=LLMDoble(), model="modelo-x",
                                 cache=InMemoryLabelCache()).values()
        self.assertEqual(etiqueta.labeler, f"{LABELER_VERSION}/modelo-x")


class LLMQueSeCorta(LLMDoble):
    """Reproduce el truncado real: un lote de más de `tope` ítems se corta."""

    def __init__(self, tope):
        super().__init__()
        self.tope = tope

    def generate_json(self, prompt, schema, **kwargs):
        from core.llm.base import LLMTruncated

        entrada = json.loads(prompt[prompt.index("["):])
        if len(entrada) > self.tope:
            self.lotes.append([e["id"] for e in entrada])
            raise LLMTruncated("se cortó al agotar el límite de salida")
        return super().generate_json(prompt, schema, **kwargs)


class TestTruncado(unittest.TestCase):
    """B1: un lote truncado se parte por la mitad y se reintenta solo esa mitad."""

    def test_el_etiquetado_pide_un_presupuesto_de_razonamiento(self):
        from core.judge.labels import LABEL_THINKING_BUDGET

        doble = LLMDoble()
        label_items([item_de(GOLDEN[0])], provider=doble, model="m", cache=InMemoryLabelCache())
        self.assertEqual(doble.presupuestos, [LABEL_THINKING_BUDGET])

    def test_un_lote_truncado_se_parte_hasta_que_cabe(self):
        doble = LLMQueSeCorta(tope=5)
        items = [item_de(d) for d in GOLDEN[:20]]
        etiquetas = label_items(items, provider=doble, model="m", cache=InMemoryLabelCache(),
                                batch_size=20)
        self.assertEqual([len(lote) for lote in doble.lotes], [20, 10, 5, 5, 10, 5, 5])
        self.assertTrue(all(e.undetermined_reason is None for e in etiquetas.values()))

    def test_si_no_cabe_ni_partiendo_queda_truncado_con_su_motivo(self):
        from core.judge.labels import TRUNCATION_MAX_SPLITS

        doble = LLMQueSeCorta(tope=0)
        items = [item_de(d) for d in GOLDEN[:8]]
        etiquetas = label_items(items, provider=doble, model="m", cache=InMemoryLabelCache(),
                                batch_size=8)
        self.assertEqual({e.undetermined_reason for e in etiquetas.values()}, {"llm_truncated"})
        self.assertEqual(len(doble.lotes), 2 ** (TRUNCATION_MAX_SPLITS + 1) - 1, "con tope de llamadas")


class TestConcordancia(unittest.TestCase):
    def test_el_doble_perfecto_concuerda_al_100(self):
        items = [item_de(d) for d in GOLDEN]
        etiquetas = label_items(items, provider=LLMDoble(), model="m", cache=InMemoryLabelCache())
        medida = agreement(GOLDEN, {i.id.split(":", 1)[1]: etiquetas[i.id] for i in items})
        self.assertEqual(medida.per_field, {"is_pain": 1.0, "intent": 1.0,
                                            "workaround_described": 1.0, "wtp_signal": 1.0})
        self.assertEqual((medida.items, medida.coverage), (64, 1.0))

    def test_los_errores_y_los_undetermined_bajan_la_concordancia(self):
        por_texto = {d["text"]: json.loads(json.dumps(d)) for d in GOLDEN}
        for dorado in list(por_texto.values())[:4]:  # 4 errores de wtp inventados por el doble
            dorado["expected"]["wtp_signal"] = not dorado["expected"]["wtp_signal"]
            dorado["spans"]["wtp_signal"] = dorado["text"][:25]
        items = [item_de(d) for d in GOLDEN]
        etiquetas = label_items(items, provider=LLMDoble(por_texto=por_texto), model="m",
                                cache=InMemoryLabelCache())
        medida = agreement(GOLDEN, {i.id.split(":", 1)[1]: etiquetas[i.id] for i in items})
        self.assertAlmostEqual(medida.per_field["wtp_signal"], 60 / 64)
        self.assertEqual(medida.per_field["is_pain"], 1.0)


if __name__ == "__main__":
    unittest.main()
