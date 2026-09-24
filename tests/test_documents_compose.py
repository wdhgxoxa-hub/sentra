"""
Composición del dossier y del plan (E5)
=======================================

El código monta el documento: secciones fijas y en orden, citas verificadas
(una afirmación que cita evidencia ajena se retira y se dice cuántas), la
evidencia citada con fecha y atribución, la viabilidad como estimación del
modelo, la procedencia, la franja del plan forzado y la marca de agua solo
con datos de demostración. El modelo solo aporta el texto de mercado.
"""

import unittest
from datetime import UTC, datetime
from typing import Any

from core.documents.claims import VIABILITY_CRITERIA, DossierLLM, PlanLLM
from core.documents.compose import PlanNotRecommended, compose_dossier, compose_plan

AHORA = datetime(2026, 9, 23, 18, 0, tzinfo=UTC)


def pieza(id_, fuente="hackernews", demo=False):
    return {"id": id_, "source": fuente, "community": "Ask HN", "kind": "post",
            "title": f"Título de {id_}", "text": f"Queja inventada de {id_}: se tarda muchísimo.",
            "url": f"https://example.com/{id_}", "created_at": datetime(2026, 9, 1, tzinfo=UTC),
            "data_source": "demo" if demo else "real",
            "attribution": {"badge": "Hacker News", "site": "Ask HN", "url": f"https://example.com/{id_}"},
            "author_key": f"autor-de-{id_}"}


def detalle(verdict="CONSTRUIR", demo=False, **cambios: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "11111111-1111-1111-1111-111111111111", "run_id": "22222222-2222-2222-2222-222222222222",
        "keywords": ["facturas", "exportar", "manual"], "verdict": verdict,
        "rule": "7: pasan todas" if verdict == "CONSTRUIR" else "5: fallan G1, G2 o G5",
        "score": 61.5, "missing": [] if verdict == "CONSTRUIR" else ["G1"],
        "weights_version": "judge-weights-v1", "labeler_version": "labels-v2/gemini-3.8-flash",
        "clustering_version": "clustering-v2",
        "gates": [{"gate": f"G{n}", "passed": True, "value": 3, "threshold": 2,
                   "evidence_ids": ["hackernews:1"]} for n in range(1, 9)],
        "dimensions": [{"name": "frecuencia", "value": 3, "normalized": 0.1, "item_ids": [], "note": None}],
        "advocate": {"verdict_before": verdict, "verdict_after": verdict, "downgraded": False,
                     "reason": None, "arguments": [{"claim": "muestra pequeña",
                                                    "evidence_ids": ["hackernews:1"], "severity": "menor"}],
                     "discarded": []},
        "evidence": [pieza("hackernews:1", demo=demo), pieza("stackexchange:2", "stackexchange"),
                     pieza("discourse:3", "discourse")],
        "run": {"id": "22222222-2222-2222-2222-222222222222", "started_at": AHORA,
                "parameters": {"topic": "facturas"}, "data_source": "real", "trigger_source": "multifuente"},
        "current_versions": {"labeler": "labels-v2", "clustering": "clustering-v2",
                             "weights": "judge-weights-v1"},
    }
    base.update(cambios)
    return base


def cita(*ids, texto="afirmación"):
    return {"text": texto, "evidence_ids": list(ids)}


def dossier_llm(**cambios: Any) -> DossierLLM:
    base: dict[str, Any] = {
        "problem_name": "Exportar facturas a mano",
        "problem": [cita("hackernews:1", texto="Exportar facturas cuesta horas"),
                    cita("hackernews:1", "reddit:999", texto="Afirmación mal citada")],
        "who": [cita("stackexchange:2", texto="Pymes con contable externo")],
        "current_solutions": [cita("discourse:3", texto="Hojas de cálculo a mano")],
        "why_now": [cita("inventado:1", texto="Solo con cita inventada")],
        "risks": [cita("hackernews:1", texto="Mercado pequeño")],
        "viability": [{"criterion": c, "score": n + 1, "reason": f"motivo {c}"}
                      for n, c in enumerate(VIABILITY_CRITERIA)],
    }
    base.update(cambios)
    return DossierLLM.model_validate(base)


def plan_llm() -> PlanLLM:
    return PlanLLM.model_validate({
        "what_and_for_whom": [cita("hackernews:1", texto="Exportador para pymes")],
        "mvp_in": [cita("hackernews:1", texto="Exportar a CSV")],
        "mvp_out": [cita("stackexchange:2", texto="Integración con bancos")],
        "stack": [{"component": "backend", "choice": "FastAPI", "reason": "rápido"}],
        "architecture": ["API REST + PostgreSQL"],
        "data_model": [{"name": "Factura", "fields": ["id", "importe"], "purpose": "guardar"}],
        "steps": [{"number": n, "objective": f"objetivo {n}", "files": [f"app/paso{n}.py"],
                   "commands": [f"pytest tests/test_paso{n}.py"], "acceptance_tests": [f"test_paso{n}"],
                   "done_criterion": f"hecho {n}"} for n in range(1, 11)],
        "validation": [cita("discourse:3", texto="10 pymes lo usan una semana")],
        "publication": [cita("hackernews:1", texto="Publicarlo en Ask HN")],
    })


def textos_de(doc) -> str:
    return doc.to_markdown()


class TestDossier(unittest.TestCase):
    def test_secciones_fijas_y_en_orden(self):
        doc = compose_dossier(detalle(), dossier_llm(), "es", model="gemini-pro", generated_at=AHORA)
        self.assertEqual([s.id for s in doc.sections], [
            "resumen", "problema", "quien", "soluciones", "por_que_ahora", "compuertas",
            "abogado", "viabilidad", "riesgos", "evidencia", "procedencia"])
        self.assertTrue(all(s.title.startswith(f"{n}. ") for n, s in enumerate(doc.sections, 1)))

    def test_una_cita_ajena_retira_la_afirmacion_y_se_dice(self):
        md = textos_de(compose_dossier(detalle(), dossier_llm(), "es", model="m", generated_at=AHORA))
        self.assertIn("Exportar facturas cuesta horas [hackernews:1]", md)
        self.assertNotIn("Afirmación mal citada", md)
        self.assertNotIn("Solo con cita inventada", md)
        self.assertIn("2 afirmaciones retiradas por citar evidencia que no es de este veredicto", md)

    def test_el_titulo_es_el_nombre_del_problema_y_se_dice_quien_lo_puso(self):
        # E8: el título salía de las palabras del grupo («week, morning»).
        doc = compose_dossier(detalle(), dossier_llm(), "es", model="m", generated_at=AHORA)
        self.assertEqual(doc.title, "Dossier · Exportar facturas a mano")
        portada = dict(doc.cover)
        self.assertEqual(portada["Nicho"], "Exportar facturas a mano (nombre propuesto por el modelo)")
        self.assertEqual(portada["Palabras del grupo"], "facturas, exportar, manual")

    def test_lo_que_dice_un_solo_autor_es_una_anecdota(self):
        # Dos piezas del mismo autor no son dos fuentes.
        evidencia = [pieza("hackernews:1"), pieza("stackexchange:2", "stackexchange"),
                     {**pieza("discourse:3", "discourse"), "author_key": "autor-de-hackernews:1"}]
        llm = dossier_llm(problem=[cita("hackernews:1", "discourse:3", texto="Cuesta horas"),
                                   cita("hackernews:1", "stackexchange:2", texto="Lo sufren muchos")])
        md = textos_de(compose_dossier(detalle(evidence=evidencia), llm, "es", model="m", generated_at=AHORA))
        self.assertIn("Anécdota (1 autor): Cuesta horas [hackernews:1, discourse:3]", md)
        self.assertIn("- Lo sufren muchos [hackernews:1, stackexchange:2]", md)

    def test_los_riesgos_empiezan_por_las_compuertas_que_fallan_con_su_evidencia(self):
        # E8: «Riesgos» salía vacío y nada explicaba G7 ni citaba la pieza que la decide.
        compuertas = [{"gate": "G7", "passed": False, "value": 1.0, "threshold": 0.5,
                       "evidence_ids": ["hackernews:99"], "measured": True,
                       "note": "TallyBird: 3 de 3 autores lo dan por bueno"}]
        lanzamiento = {**pieza("hackernews:99"), "text": "Presentamos un asistente gratuito que persigue facturas."}
        llm = dossier_llm(risks=[cita("inventado:1", texto="Riesgo sin respaldo")])
        doc = compose_dossier(detalle(verdict="DESCARTAR", gates=compuertas, gate_evidence=[lanzamiento]),
                              llm, "es", model="m", generated_at=AHORA)
        riesgos = next(s for s in doc.sections if s.id == "riesgos")
        texto = "\n".join(b.text + " ".join(b.items) for b in riesgos.blocks)
        self.assertIn("G7 (saturación)", texto)
        # Pendiente de E8: en palabras, qué exige la compuerta, y su nota.
        self.assertIn("exige que ningún competidor gratuito", texto)
        self.assertIn("TallyBird: 3 de 3 autores lo dan por bueno", texto)
        self.assertIn("[hackernews:99]", texto)
        self.assertNotIn("Sin afirmaciones verificables", texto)
        evidencia = next(s for s in doc.sections if s.id == "evidencia")
        self.assertIn("hackernews:99", "\n".join(b.signature for b in evidencia.blocks))

    def test_lo_que_exige_cada_compuerta_sigue_a_los_umbrales_del_juez(self):
        from core.documents.compose import ROTULOS
        from core.judge.gates import (
            CONCENTRATION_MAX_SHARE,
            MIN_AUTORES_COMPETIDOR,
            MIN_DISTINCT_SOURCES,
            RECENCY_DAYS,
        )

        numeros = {1: "dos", 2: "dos", 3: "tres"}
        es = ROTULOS["es"]["gate_rules"]
        self.assertIn(numeros[MIN_DISTINCT_SOURCES], es["G1"])
        self.assertIn(f"{round(CONCENTRATION_MAX_SHARE * 100)} %", es["G5"])
        self.assertIn(f"{RECENCY_DAYS} días", es["G6"])
        self.assertIn(numeros[MIN_AUTORES_COMPETIDOR], es["G7"])
        self.assertEqual(set(es), set(ROTULOS["en"]["gate_rules"]), "las mismas compuertas en los dos idiomas")

    def test_una_seccion_sin_afirmaciones_validas_no_se_rellena(self):
        doc = compose_dossier(detalle(), dossier_llm(), "es", model="m", generated_at=AHORA)
        ahora = next(s for s in doc.sections if s.id == "por_que_ahora")
        self.assertEqual([b.text for b in ahora.blocks if b.kind == "note"], ["Sin afirmaciones verificables."])

    def test_la_evidencia_citada_con_fecha_y_atribucion(self):
        doc = compose_dossier(detalle(), dossier_llm(), "es", model="m", generated_at=AHORA)
        evidencia = next(s for s in doc.sections if s.id == "evidencia")
        texto = "\n".join(b.text + " ".join(b.items) + b.signature for b in evidencia.blocks)
        self.assertIn("hackernews:1", texto)
        self.assertIn("2026-09-01", texto)
        self.assertIn("Hacker News · Ask HN · https://example.com/hackernews:1", texto)

    def test_la_evidencia_de_stack_exchange_lleva_su_licencia_y_no_su_autor(self):
        # AUD2-018 (DP5 A): CC BY-SA 4.0 y enlace al original; el autor, siguiendo
        # el enlace (R9: nunca en claro).
        from core.sources.attribution import attribution_fields

        se = {**pieza("stackexchange:2", "stackexchange"), "author_hash": "a" * 64,
              "attribution": attribution_fields("stackexchange", "Stack Overflow",
                                                "https://stackoverflow.com/q/2")}
        doc = compose_dossier(detalle(evidence=[pieza("hackernews:1"), se]),
                              dossier_llm(), "es", model="m", generated_at=AHORA)
        evidencia = next(s for s in doc.sections if s.id == "evidencia")
        firmas = [b.signature for b in evidencia.blocks if "stackexchange:2" in b.signature]
        self.assertTrue(firmas, "la pieza de Stack Exchange no aparece citada")
        self.assertIn("CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/)", firmas[0])
        self.assertIn("https://stackoverflow.com/q/2", firmas[0])
        self.assertNotIn("a" * 64, firmas[0])

    def test_un_grupo_sin_problema_comun_no_lleva_puntuacion(self):
        doc = compose_dossier(detalle(verdict="DESCARTAR", score=None, rule="0: no es un mismo problema (G0)"),
                              dossier_llm(), "es", model="m", generated_at=AHORA)
        texto = textos_de(doc)
        self.assertIn("sin problema común", texto)
        self.assertNotIn("None", texto)

    def test_la_viabilidad_es_una_estimacion_del_modelo(self):
        doc = compose_dossier(detalle(), dossier_llm(), "es", model="m", generated_at=AHORA)
        viabilidad = next(s for s in doc.sections if s.id == "viabilidad")
        self.assertIn("estimación del modelo", viabilidad.title.lower())
        self.assertIn("no cambia el veredicto", viabilidad.blocks[0].text)
        filas = next(b for b in viabilidad.blocks if b.kind == "table").rows
        self.assertEqual(len(filas), 5)
        self.assertIn("5/5", filas[-1][1])

    def test_la_procedencia_dice_de_donde_sale_todo(self):
        md = textos_de(compose_dossier(detalle(), dossier_llm(), "es", model="gemini-pro",
                                       generated_at=AHORA))
        for dato in ("22222222-2222-2222-2222-222222222222", "clustering-v2", "labels-v2",
                     "judge-weights-v1", "gemini-pro", "2026-09-23"):
            self.assertIn(dato, md)

    def test_marca_de_agua_solo_con_demostracion(self):
        real = compose_dossier(detalle(), dossier_llm(), "es", model="m", generated_at=AHORA)
        demo = compose_dossier(detalle(demo=True), dossier_llm(), "es", model="m", generated_at=AHORA)
        self.assertEqual((real.data_source, real.watermark), ("real", None))
        self.assertEqual(demo.data_source, "demo")
        self.assertIsNotNone(demo.watermark)

    def test_sirve_para_cualquier_veredicto_y_en_ingles(self):
        doc = compose_dossier(detalle("DESCARTAR"), dossier_llm(), "en", model="m", generated_at=AHORA)
        self.assertIsNone(doc.stripe)
        self.assertEqual(doc.sections[0].title, "1. Verdict summary")
        self.assertIn("DESCARTAR", textos_de(doc))


class TestPlan(unittest.TestCase):
    def test_solo_para_construir_salvo_que_se_fuerce(self):
        with self.assertRaises(PlanNotRecommended):
            compose_plan(detalle("INVESTIGAR MÁS"), plan_llm(), "es", model="m", generated_at=AHORA)
        forzado = compose_plan(detalle("INVESTIGAR MÁS"), plan_llm(), "es", model="m",
                               generated_at=AHORA, forced=True)
        self.assertEqual(forzado.stripe,
                         "El juez no recomienda construir este nicho: INVESTIGAR MÁS — 5: fallan G1, G2 o G5")
        self.assertIsNone(compose_plan(detalle(), plan_llm(), "es", model="m", generated_at=AHORA).stripe)

    def test_secciones_fijas_y_los_diez_pasos_completos(self):
        doc = compose_plan(detalle(), plan_llm(), "es", model="m", generated_at=AHORA)
        self.assertEqual([s.id for s in doc.sections], [
            "que", "mvp", "stack", "arquitectura", "datos", "pasos", "validacion", "publicacion",
            "procedencia"])
        md = textos_de(doc)
        for n in range(1, 11):
            self.assertIn(f"### Paso {n}: objetivo {n}", md)
            self.assertIn(f"pytest tests/test_paso{n}.py", md)
            self.assertIn(f"| Hecho cuando | hecho {n} |", md)
        self.assertIn("Exportar a CSV [hackernews:1]", md)

    def test_en_ingles(self):
        doc = compose_plan(detalle(), plan_llm(), "en", model="m", generated_at=AHORA)
        self.assertIn("### Step 1: objetivo 1", textos_de(doc))


if __name__ == "__main__":
    unittest.main()
