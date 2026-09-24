"""
Esquemas estrictos y citas verificadas (E3)
===========================================

Lo que el modelo devuelve para el dossier y el plan se valida con Pydantic
(sin campos de más, con los límites fijados) y cada afirmación de mercado
lleva ids de evidencia. Una afirmación con un id que no es de ese veredicto
se retira entera: citar mal invalida lo afirmado, no se «arregla».
"""

import unittest

from pydantic import ValidationError

from core.documents.claims import (
    VIABILITY_CRITERIA,
    Claim,
    DossierLLM,
    DossierPartA,
    DossierPartB,
    PlanLLM,
    PlanPartA,
    PlanPartB,
    verify_claims,
)

VALIDOS = {"hackernews:1", "stackexchange:2", "discourse:3"}


def viabilidad(**cambios):
    base = [{"criterion": c, "score": 3, "reason": "razón"} for c in VIABILITY_CRITERIA]
    for c, nota in cambios.items():
        next(v for v in base if v["criterion"] == c)["score"] = nota
    return base


def paso(n):
    return {"number": n, "objective": f"objetivo {n}", "files": ["app/main.py"],
            "commands": ["pytest"], "acceptance_tests": ["test_x"], "done_criterion": "pasa"}


def plan(**cambios):
    cita = [{"text": "x", "evidence_ids": ["hackernews:1"]}]
    base = {"what_and_for_whom": cita, "mvp_in": cita, "mvp_out": cita,
            "stack": [{"component": "backend", "choice": "FastAPI", "reason": "r"}],
            "architecture": ["API y base de datos"],
            "data_model": [{"name": "Factura", "fields": ["id", "importe"], "purpose": "p"}],
            "steps": [paso(n) for n in range(1, 11)], "validation": cita, "publication": cita}
    base.update(cambios)
    return base


class TestCitas(unittest.TestCase):
    def test_las_afirmaciones_bien_citadas_se_quedan(self):
        buenas = [Claim(text="a", evidence_ids=["hackernews:1"]),
                  Claim(text="b", evidence_ids=["stackexchange:2", "discourse:3"])]
        quedan, retiradas = verify_claims(buenas, VALIDOS)
        self.assertEqual((quedan, retiradas), (buenas, []))

    def test_un_solo_id_inventado_retira_la_afirmacion_entera(self):
        mixta = Claim(text="c", evidence_ids=["hackernews:1", "reddit:999"])
        quedan, retiradas = verify_claims([mixta], VALIDOS)
        self.assertEqual((quedan, retiradas), ([], [mixta]))

    def test_sin_citas_no_hay_afirmacion(self):
        with self.assertRaises(ValidationError):
            Claim(text="sin cita", evidence_ids=[])

    def test_los_ids_repetidos_se_quedan_una_vez(self):
        quedan, _ = verify_claims([Claim(text="d", evidence_ids=["hackernews:1", "hackernews:1"])],
                                  VALIDOS)
        self.assertEqual(quedan[0].evidence_ids, ["hackernews:1"])


class TestDossier(unittest.TestCase):
    def dossier(self, **cambios):
        cita = [{"text": "x", "evidence_ids": ["hackernews:1"]}]
        base = {"problem": cita, "who": cita, "current_solutions": cita, "why_now": cita,
                "risks": cita, "viability": viabilidad()}
        base.update(cambios)
        return DossierLLM.model_validate(base)

    def test_un_dossier_completo_valida(self):
        self.assertEqual(len(self.dossier().viability), len(VIABILITY_CRITERIA))

    def test_la_viabilidad_trae_los_cinco_criterios_una_vez_cada_uno(self):
        with self.assertRaises(ValidationError):
            self.dossier(viability=viabilidad()[:4])
        repetido = viabilidad()
        repetido[4] = dict(repetido[0])
        with self.assertRaises(ValidationError):
            self.dossier(viability=repetido)

    def test_la_nota_va_de_1_a_5(self):
        with self.assertRaises(ValidationError):
            self.dossier(viability=viabilidad(riesgo_legal=6))

    def test_no_admite_campos_de_mas(self):
        with self.assertRaises(ValidationError):
            self.dossier(conclusion="el modelo añade lo que quiere")


class TestPlan(unittest.TestCase):
    def test_un_plan_completo_valida(self):
        self.assertEqual([p.number for p in PlanLLM.model_validate(plan()).steps], list(range(1, 11)))

    def test_exactamente_diez_pasos_numerados_en_orden(self):
        with self.assertRaises(ValidationError):
            PlanLLM.model_validate(plan(steps=[paso(n) for n in range(1, 10)]))
        with self.assertRaises(ValidationError):
            PlanLLM.model_validate(plan(steps=[paso(n) for n in (1, 2, 3, 4, 5, 6, 7, 8, 10, 9)]))

    def test_cada_paso_trae_archivos_comandos_pruebas_y_criterio_de_hecho(self):
        incompleto = paso(1)
        incompleto["acceptance_tests"] = []
        with self.assertRaises(ValidationError):
            PlanLLM.model_validate(plan(steps=[incompleto] + [paso(n) for n in range(2, 11)]))


class TestMitades(unittest.TestCase):
    """Si la respuesta se trunca, el esquema se pide en dos mitades: entre las
    dos tienen que cubrir todo, sin solaparse."""

    def test_las_mitades_cubren_el_esquema_entero(self):
        for entero, a, b in ((DossierLLM, DossierPartA, DossierPartB), (PlanLLM, PlanPartA, PlanPartB)):
            with self.subTest(esquema=entero.__name__):
                campos_a, campos_b = set(a.model_fields), set(b.model_fields)
                self.assertEqual(campos_a & campos_b, set())
                self.assertEqual(campos_a | campos_b, set(entero.model_fields))


if __name__ == "__main__":
    unittest.main()
