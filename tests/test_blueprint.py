"""Tests del sintetizador de especificaciones de proyecto (PRD)."""

import unittest
from typing import Any, ClassVar

from core.intelligence.blueprint import build_blueprint


def cluster_base(**cambios):
    """Cluster realista, con la forma que devuelve la base de datos."""
    base = {
        "cluster_key": "complaint:invoice|manual",
        "label": "invoice + manual",
        "intent_type": "complaint",
        "keywords": ["invoice", "manual"],
        "subreddits": ["SaaS", "accounting", "bookkeeping", "freelance", "smallbusiness"],
        "mention_count": 5,
        "community_count": 5,
        "job_statement": (
            "Cuando los profesionales enfrentan 'Manual invoice export is broken', "
            "necesitan ejecutar la tarea con menor friccion"
        ),
        "current_solutions": [],
        "risk_flags": [],
        "spread_factor": 1.0,
        "frequency_factor": 0.8,
        "severity_factor": 1.0,
        "recency_factor": 0.9,
        "paid_signal_factor": 1.0,
        "final_score": 80.0,
        "urgency_tier": "CRITICAL",
        "evidence": [
            {
                "quote": "Manual invoice export is broken and I would pay for a fix",
                "subreddit": "smallbusiness",
                "author": "ana",
                "url": "https://reddit.com/t3_demo0",
            },
            {
                "quote": "Reconciling invoices by hand every month eats a whole day",
                "subreddit": "accounting",
                "author": "luis",
                "url": "https://reddit.com/t3_demo1",
            },
        ],
    }
    base.update(cambios)
    return base


class TestEstructura(unittest.TestCase):
    def test_genera_todas_las_secciones_con_contenido(self):
        doc = build_blueprint(cluster_base())
        for campo in (
            "product_name",
            "one_liner",
            "executive_summary",
            "problem",
            "solution",
            "why_existing_fail",
            "monetisation",
            "markdown",
        ):
            valor = getattr(doc, campo)
            self.assertTrue(valor.strip(), f"{campo} llego vacio")

    def test_el_mvp_separa_dos_fases(self):
        doc = build_blueprint(cluster_base())
        self.assertEqual(len(doc.mvp), 2)
        for fase in doc.mvp:
            self.assertTrue(fase.items, f"la fase '{fase.name}' no lleva funcionalidades")

    def test_acepta_la_grafia_camelCase_del_puente(self):
        crudo = {
            "clusterKey": "complaint:x",
            "label": "x",
            "intentType": "complaint",
            "keywords": ["export"],
            "subreddits": ["SaaS"],
            "mentionCount": 3,
            "communityCount": 1,
            "jobStatement": "algo",
            "currentSolutions": [],
            "paidSignalFactor": 0.2,
            "finalScore": 40.0,
            "urgencyTier": "MEDIUM",
            "evidence": [],
        }
        doc = build_blueprint(crudo)
        self.assertIn("3", doc.problem)


class TestEvidenciaReal(unittest.TestCase):
    def test_cita_el_volumen_y_las_comunidades_reales(self):
        doc = build_blueprint(cluster_base())
        self.assertIn("5", doc.problem)
        self.assertIn("r/accounting", doc.markdown)
        self.assertIn("r/SaaS", doc.markdown)

    def test_deduplica_citas_identicas(self):
        repetida = {
            "quote": "Manual invoice export is broken",
            "subreddit": "SaaS",
            "author": "ana",
            "url": "u",
        }
        doc = build_blueprint(cluster_base(evidence=[repetida, dict(repetida), dict(repetida)]))
        self.assertEqual(len(doc.evidence), 1)

    def test_distingue_menciones_de_citas_distintas(self):
        """5 menciones de un mismo texto no son 5 pruebas: hay que decirlo."""
        repetida = {"quote": "mismo texto", "subreddit": "SaaS", "author": "a", "url": "u"}
        doc = build_blueprint(
            cluster_base(mention_count=5, evidence=[repetida, dict(repetida)])
        )
        self.assertEqual(doc.distinct_quotes, 1)
        self.assertIn("1", doc.problem)


class TestSinDatos(unittest.TestCase):
    def test_sin_soluciones_actuales_lo_dice_y_no_inventa(self):
        doc = build_blueprint(cluster_base(current_solutions=[]))
        self.assertTrue(doc.why_existing_fail.strip())
        for inventado in ("Excel", "Zapier", "QuickBooks", "Notion"):
            self.assertNotIn(inventado, doc.why_existing_fail)

    def test_con_soluciones_actuales_las_nombra(self):
        doc = build_blueprint(cluster_base(current_solutions=["a spreadsheet", "zapier"]))
        self.assertIn("spreadsheet", doc.why_existing_fail.lower())

    def test_sin_evidencia_no_revienta(self):
        doc = build_blueprint(cluster_base(evidence=[]))
        self.assertEqual(doc.evidence, [])
        self.assertTrue(doc.markdown.strip())


class TestMonetizacion(unittest.TestCase):
    def test_senal_de_pago_alta_y_nula_dan_recomendaciones_distintas(self):
        alta = build_blueprint(cluster_base(paid_signal_factor=1.0)).monetisation
        nula = build_blueprint(cluster_base(paid_signal_factor=0.0)).monetisation
        self.assertNotEqual(alta, nula)

    def test_sin_senal_de_pago_avisa_en_lugar_de_proponer_precio(self):
        doc = build_blueprint(cluster_base(paid_signal_factor=0.0))
        self.assertNotIn("$", doc.monetisation)


class TestIdioma(unittest.TestCase):
    def test_en_ingles_no_deja_frases_en_espanol(self):
        doc = build_blueprint(cluster_base(), language="en")
        for palabra in (" comunidades", " quejas", " para que", "Resumen"):
            self.assertNotIn(palabra, doc.markdown)

    def test_el_espanol_es_el_idioma_por_defecto(self):
        doc = build_blueprint(cluster_base())
        self.assertIn("Resumen", doc.markdown)

    def test_idioma_desconocido_cae_al_espanol(self):
        doc = build_blueprint(cluster_base(), language="fr")
        self.assertIn("Resumen", doc.markdown)


class TestMarkdown(unittest.TestCase):
    def test_el_markdown_lleva_titulos_y_el_nombre_del_producto(self):
        doc = build_blueprint(cluster_base())
        # AUD-009: la primera linea declara la fuente de los datos; el titulo
        # va justo despues.
        lineas = doc.markdown.splitlines()
        self.assertTrue(lineas[0].startswith("> "))
        self.assertTrue(lineas[2].startswith("# "))
        self.assertIn(doc.product_name, doc.markdown)
        self.assertGreaterEqual(doc.markdown.count("## "), 5)

    def test_serializa_a_diccionario_para_el_puente(self):
        doc = build_blueprint(cluster_base())
        datos = doc.to_dict()
        self.assertEqual(datos["productName"], doc.product_name)
        self.assertIsInstance(datos["mvp"], list)
        self.assertIsInstance(datos["evidence"], list)


if __name__ == "__main__":
    unittest.main()


class TestRedaccion(unittest.TestCase):
    """El documento lo lee una persona: la concordancia no es un detalle."""

    def _una_cita(self, **cambios):
        cita = {"quote": "algo roto", "subreddit": "SaaS", "author": "ana", "url": "u"}
        return cluster_base(evidence=[cita], **cambios)

    def test_singular_en_espanol(self):
        doc = build_blueprint(self._una_cita(mention_count=1, subreddits=["SaaS"]))
        for mal in ("1 personas", "1 testimonios", "1 menciones", "1 comunidades"):
            self.assertNotIn(mal, doc.markdown, f"concordancia rota: «{mal}»")

    def test_singular_en_ingles(self):
        doc = build_blueprint(
            self._una_cita(mention_count=1, subreddits=["SaaS"]), language="en"
        )
        for mal in ("1 people", "1 accounts", "1 mentions", "1 forums"):
            self.assertNotIn(mal, doc.markdown, f"concordancia rota: «{mal}»")

    def test_plural_sigue_bien(self):
        doc = build_blueprint(cluster_base())
        self.assertIn("5 comunidades", doc.markdown)

    def test_las_citas_de_varias_lineas_no_rompen_el_blockquote(self):
        cita = {
            "quote": "Primera linea\nSegunda linea\nTercera",
            "subreddit": "SaaS",
            "author": "ana",
            "url": "u",
        }
        doc = build_blueprint(cluster_base(evidence=[cita]))
        dentro = False
        for linea in doc.markdown.splitlines():
            if linea.startswith(">"):
                dentro = True
                continue
            if dentro and linea.strip() == "":
                dentro = False
                continue
            if dentro:
                self.fail(f"linea de cita fuera del blockquote: {linea!r}")
        self.assertIn("> Segunda linea", doc.markdown)


class TestFormaRealDelPuente(unittest.TestCase):
    """La forma que manda Rust de verdad: los factores van anidados.

    El struct `OpportunityCluster` agrupa la puntuacion en `breakdown`. Un test
    con el cluster aplanado pasaba y el documento salia con ceros, que es la
    peor forma de fallar: parece un dato medido.
    """

    ANIDADO: ClassVar[dict[str, Any]] = {
        "clusterKey": "complaint:invoice|manual",
        "label": "invoice + manual",
        "intentType": "complaint",
        "keywords": ["invoice", "manual"],
        "subreddits": ["SaaS", "accounting", "bookkeeping"],
        "mentionCount": 5,
        "communityCount": 3,
        "jobStatement": "algo",
        "currentSolutions": [],
        "urgencyTier": "HIGH",
        "breakdown": {
            "spreadFactor": 1.0,
            "frequencyFactor": 0.2,
            "severityFactor": 1.0,
            "recencyFactor": 1.0,
            "paidSignalFactor": 0.6,
            "rawScore": 74.0,
            "finalScore": 74.0,
        },
        "evidence": [
            {"quote": "uno", "subreddit": "SaaS", "author": "a", "url": "1"},
            {"quote": "dos", "subreddit": "accounting", "author": "b", "url": "2"},
        ],
    }

    def test_lee_la_puntuacion_de_dentro_de_breakdown(self):
        doc = build_blueprint(self.ANIDADO)
        self.assertIn("74", doc.executive_summary)
        self.assertNotIn("intensidad de 0", doc.executive_summary)

    def test_lee_los_factores_de_dentro_de_breakdown(self):
        doc = build_blueprint(self.ANIDADO)
        self.assertIn("100 %", doc.problem)
        self.assertNotIn("del 0 %", doc.problem)

    def test_la_senal_de_pago_anidada_llega_a_la_monetizacion(self):
        alto = build_blueprint(self.ANIDADO).monetisation
        bajo_cluster = dict(self.ANIDADO)
        bajo_cluster["breakdown"] = dict(self.ANIDADO["breakdown"], paidSignalFactor=0.0)
        self.assertNotEqual(alto, build_blueprint(bajo_cluster).monetisation)

    def test_el_nivel_superior_sigue_teniendo_prioridad(self):
        """La fila de PostgreSQL trae los campos sueltos: no debe romperse."""
        plano = dict(self.ANIDADO, final_score=99.0)
        del plano["breakdown"]
        self.assertIn("99", build_blueprint(plano).executive_summary)


class TestNoInflarElCaso(unittest.TestCase):
    def test_si_cada_mencion_es_un_texto_distinto_no_dice_no_sobre_n(self):
        """«se sostiene sobre 5 testimonios, no sobre 5» no significa nada."""
        citas = [
            {"quote": f"queja {i}", "subreddit": "SaaS", "author": "a", "url": str(i)}
            for i in range(5)
        ]
        doc = build_blueprint(cluster_base(mention_count=5, evidence=citas))
        self.assertNotIn("no sobre 5", doc.problem)

    def test_si_hay_repeticion_si_lo_advierte(self):
        # AUD-009: la repeticion solo se afirma si las citas cubren TODAS las
        # menciones (aqui 5 de 5). Con 2 citas de 5 menciones no se sabe nada
        # de las otras 3 y la version anterior afirmaba algo falso.
        repetida = {"quote": "igual", "subreddit": "SaaS", "author": "a", "url": "u"}
        otra = {"quote": "otra", "subreddit": "SaaS", "author": "b", "url": "v"}
        doc = build_blueprint(
            cluster_base(mention_count=5, evidence=[dict(repetida)] * 4 + [otra])
        )
        self.assertIn("no en 5", doc.problem)

    def test_con_menos_citas_que_menciones_no_afirma_repeticion(self):
        repetida = {"quote": "igual", "subreddit": "SaaS", "author": "a", "url": "u"}
        doc = build_blueprint(
            cluster_base(mention_count=5, evidence=[repetida, dict(repetida)])
        )
        self.assertNotIn("repiten", doc.problem)
