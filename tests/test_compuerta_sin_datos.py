"""
Una compuerta que no midió nada no se pinta como aprobada (AUD2-005)
===================================================================

G7 («ningún competidor gratuito que la mayoría da por bueno») pasaba en los
9 veredictos reales con 0 evidencias: nadie mencionaba un competidor
gratuito. Para decidir es correcto no castigar la falta de datos, pero la
interfaz y el dossier la enseñaban con un ✓ como si se hubiera verificado.
Ahora la compuerta dice si midió (`measured`); los veredictos guardados sin
ese campo se normalizan al leerlos: solo G7 puede aprobar por ausencia.
"""

import unittest
from datetime import UTC, datetime

from core.documents.compose import compose_dossier
from core.judge.gates import judge_cluster, normalizar_compuertas
from core.judge.labels import VerifiedCompetitor
from tests.test_documents_compose import detalle, dossier_llm
from tests.test_judge_verdict import AHORA, etiqueta, grupo_construir


def g7(resultado):
    return next(g for g in resultado.gates if g.gate == "G7")


class TestG7Medida(unittest.TestCase):
    def test_sin_competidores_gratuitos_pasa_pero_no_midio(self):
        resultado = judge_cluster(*grupo_construir(), now=AHORA)
        self.assertTrue(g7(resultado).passed)
        self.assertFalse(g7(resultado).measured)
        self.assertEqual(resultado.verdict, "CONSTRUIR", "la falta de datos no castiga")

    def test_con_un_competidor_gratuito_de_tres_autores_si_mide(self):
        # Regla de 3 autores (aprobada tras E8): con menos, el competidor no cuenta.
        items, etiquetas = grupo_construir()
        gratis = VerifiedCompetitor(name="TallyBird", stance="queja", free=True, evidence_span="TallyBird")
        for i in items[4:7]:
            etiquetas[i.id] = etiqueta(i.id, competidores=[gratis])
        resultado = judge_cluster(items, etiquetas, now=AHORA)
        self.assertTrue(g7(resultado).measured)
        self.assertEqual(resultado.verdict, "CONSTRUIR", "quejas del competidor: no satura")

    def test_un_solo_autor_que_se_queja_de_un_competidor_no_mide_ni_frena(self):
        items, etiquetas = grupo_construir()
        gratis = VerifiedCompetitor(name="TallyBird", stance="queja", free=True, evidence_span="TallyBird")
        etiquetas[items[4].id] = etiqueta(items[4].id, competidores=[gratis])
        resultado = judge_cluster(items, etiquetas, now=AHORA)
        self.assertFalse(g7(resultado).measured)
        self.assertEqual(resultado.verdict, "CONSTRUIR", "sin menciones favorables no hay señal que resolver")

    def test_las_demas_compuertas_siempre_miden(self):
        resultado = judge_cluster(*grupo_construir(), now=AHORA)
        self.assertTrue(all(g.measured for g in resultado.gates if g.gate != "G7"))


class TestNormalizarGuardadas(unittest.TestCase):
    def test_un_veredicto_antiguo_sin_el_campo(self):
        guardadas = [
            {"gate": "G7", "passed": True, "value": 0, "threshold": 0.5, "evidence_ids": []},
            {"gate": "G7", "passed": True, "value": 0.3, "threshold": 0.5, "evidence_ids": ["a"]},
            {"gate": "G8", "passed": True, "value": 0, "threshold": 0, "evidence_ids": []},
            {"gate": "G1", "passed": False, "value": 1, "threshold": 2, "evidence_ids": ["a"]},
        ]
        self.assertEqual([g["measured"] for g in normalizar_compuertas(guardadas)], [False, True, True, True])

    def test_lo_que_ya_trae_el_campo_se_respeta(self):
        guardada = [{"gate": "G7", "passed": True, "value": 0, "threshold": 0.5, "evidence_ids": [], "measured": True}]
        self.assertTrue(normalizar_compuertas(guardada)[0]["measured"])


class TestDossier(unittest.TestCase):
    def test_la_compuerta_sin_datos_se_dice_en_el_dossier(self):
        gates = [{"gate": f"G{n}", "passed": True, "value": 3, "threshold": 2, "evidence_ids": ["hackernews:1"]}
                 for n in range(1, 7)]
        gates.append({"gate": "G7", "passed": True, "value": 0, "threshold": 0.5, "evidence_ids": [], "measured": False})
        md = compose_dossier(detalle(gates=gates), dossier_llm(), "es", model="m",
                             generated_at=datetime(2026, 9, 24, tzinfo=UTC)).to_markdown()
        self.assertIn("| G7 | sin datos", md)
        self.assertNotIn("| G7 | pasa", md)


if __name__ == "__main__":
    unittest.main()
