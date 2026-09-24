"""
Perfil de escaneo y biblioteca de frases (F2.5)
===============================================

Un escaneo ya no es «un subreddit»: es un perfil con tema, frases de
intención de dolor (versionadas, en inglés y español) y objetivos por
fuente. Sin tema, el modo descubrimiento busca solo por intención.
"""

import unittest

from pydantic import ValidationError

from core.sources.phrases import INTENTS, PHRASE_LIBRARY_VERSION, PHRASES, phrases_for
from core.sources.profile import ScanProfile, term_pairs


class TestBiblioteca(unittest.TestCase):
    def test_esta_versionada(self):
        self.assertRegex(PHRASE_LIBRARY_VERSION, r"^\d{4}-\d{2}-\d{2}\.v\d+$")

    def test_cada_intencion_tiene_frases_en_ingles_y_espanol(self):
        self.assertEqual(set(INTENTS), {"busca_herramienta", "frustracion", "parche_casero",
                                        "dispuesto_a_pagar", "alternativa"})
        for intencion in INTENTS:
            for idioma in ("en", "es"):
                with self.subTest(intencion=intencion, idioma=idioma):
                    self.assertTrue(PHRASES[intencion][idioma])

    def test_las_del_encargo_estan(self):
        self.assertIn("is there a tool", phrases_for(["busca_herramienta"], ["en"]))
        self.assertIn("existe alguna herramienta", phrases_for(["busca_herramienta"], ["es"]))
        self.assertIn("I'd pay", phrases_for(["dispuesto_a_pagar"], ["en"]))
        self.assertIn("alternative to", phrases_for(["alternativa"], ["en"]))


class TestPerfil(unittest.TestCase):
    def test_un_perfil_de_tema_produce_su_consulta(self):
        perfil = ScanProfile(name="facturas", keywords=["invoicing", "facturación"],
                             intents=["busca_herramienta"], languages=["en"],
                             targets={"stackexchange": ["superuser"]})
        consulta = perfil.to_query()
        self.assertEqual(consulta.keywords, ["invoicing", "facturación"])
        self.assertIn("is there a tool", consulta.phrases)
        self.assertNotIn("existe alguna herramienta", consulta.phrases, "solo los idiomas pedidos")
        self.assertEqual(consulta.targets, {"stackexchange": ["superuser"]})
        self.assertFalse(consulta.discovery)

    def test_el_modo_descubrimiento_no_lleva_tema(self):
        perfil = ScanProfile(name="descubrir", discovery=True)
        consulta = perfil.to_query()
        self.assertEqual(consulta.keywords, [])
        self.assertTrue(consulta.discovery)
        self.assertTrue(consulta.phrases, "todas las intenciones por defecto")

    def test_sin_tema_ni_descubrimiento_no_hay_perfil(self):
        with self.assertRaises(ValidationError):
            ScanProfile(name="vacio")

    def test_en_descubrimiento_no_se_admite_tema(self):
        with self.assertRaises(ValidationError):
            ScanProfile(name="x", keywords=["a"], discovery=True)

    def test_una_intencion_desconocida_se_rechaza(self):
        with self.assertRaises(ValidationError):
            ScanProfile.model_validate({"name": "x", "keywords": ["a"], "intents": ["inventada"]})

    def test_el_perfil_guarda_la_version_de_frases(self):
        self.assertEqual(ScanProfile(name="x", keywords=["a"]).phrase_library_version,
                         PHRASE_LIBRARY_VERSION)


class TestCombinaciones(unittest.TestCase):
    def test_reparte_por_igual_antes_de_repetir_palabra(self):
        consulta = ScanProfile(name="x", keywords=["a", "b"], intents=["alternativa"],
                               languages=["en"]).to_query()
        pares = term_pairs(consulta, limit=4)
        self.assertEqual(len(pares), 4)
        self.assertEqual([p[0] for p in pares[:2]], ["a", "b"], "cada palabra antes de repetir")

    def test_en_descubrimiento_solo_frases(self):
        consulta = ScanProfile(name="x", discovery=True, languages=["en"]).to_query()
        pares = term_pairs(consulta, limit=3)
        self.assertTrue(all(p[0] is None for p in pares))
        self.assertEqual(len({p[1] for p in pares}), 3)

    def test_nunca_mas_que_el_limite(self):
        consulta = ScanProfile(name="x", keywords=["a"]).to_query()
        self.assertLessEqual(len(term_pairs(consulta, limit=2)), 2)


if __name__ == "__main__":
    unittest.main()
