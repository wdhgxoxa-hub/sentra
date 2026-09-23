"""
Conjunto dorado del juez (F3.7)
===============================

Al menos 60 ítems inventados, en inglés y en español a partes iguales, con
etiquetas esperadas escritas antes de medir ningún modelo. Este test vigila
que el conjunto sea coherente con el esquema de etiquetas y que cada
fragmento de evidencia esperado exista literalmente en su texto: si no, el
doble «perfecto» fallaría la verificación anti-alucinación por culpa del
conjunto y no del código.
"""

import json
import unittest
from collections import Counter
from pathlib import Path

from core.judge.labels import INTENTS, STANCES, span_in_text

GOLDEN = Path(__file__).parent / "fixtures" / "golden_labels.json"


def cargar():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


class TestConjuntoDorado(unittest.TestCase):
    def test_tamano_y_reparto_por_idioma(self):
        items = cargar()["items"]
        self.assertGreaterEqual(len(items), 60)
        idiomas = Counter(i["lang"] for i in items)
        self.assertEqual(set(idiomas), {"en", "es"})
        self.assertEqual(idiomas["en"], idiomas["es"])
        self.assertEqual(len({i["id"] for i in items}), len(items), "ids únicos")

    def test_las_etiquetas_esperadas_son_validas(self):
        for dorado in cargar()["items"]:
            esperado = dorado["expected"]
            with self.subTest(id=dorado["id"]):
                self.assertIn(esperado["intent"], INTENTS)
                for campo in ("is_pain", "workaround_described", "wtp_signal"):
                    self.assertIsInstance(esperado[campo], bool)
                for competidor in esperado["competitors"]:
                    self.assertIn(competidor["stance"], STANCES)

    def test_cada_etiqueta_positiva_tiene_su_fragmento_literal(self):
        for dorado in cargar()["items"]:
            esperado, spans, texto = dorado["expected"], dorado["spans"], dorado["text"]
            with self.subTest(id=dorado["id"]):
                positivas = [c for c in ("is_pain", "workaround_described", "wtp_signal") if esperado[c]]
                if esperado["intent"] != "pregunta_neutra":
                    positivas.append("intent")
                positivas += [f"competitors.{c['name']}" for c in esperado["competitors"]]
                for etiqueta in positivas:
                    self.assertIn(etiqueta, spans)
                for etiqueta, fragmento in spans.items():
                    self.assertTrue(span_in_text(fragmento, texto), f"{etiqueta}: {fragmento!r}")

    def test_cubre_todas_las_intenciones_y_posturas(self):
        items = cargar()["items"]
        self.assertEqual({i["expected"]["intent"] for i in items}, set(INTENTS))
        posturas = {c["stance"] for i in items for c in i["expected"]["competitors"]}
        self.assertEqual(posturas, {"queja", "satisfecho"})


if __name__ == "__main__":
    unittest.main()
