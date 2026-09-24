"""
Juez, etapa 2: agrupación multifuente
=====================================

Agrupamiento determinista por similitud de embeddings multilingües (e5,
D-M2): la misma queja en inglés y en español cae en el mismo grupo si sus
vectores están cerca. Los tests usan vectores hechos a mano. Identidad
estable D-G: una lectura que comparte miembros con una anterior hereda su
UUID.
"""

import unittest
from datetime import UTC, datetime, timedelta

from core.evidence.model import EvidenceItem
from core.judge.clustering import (
    CLUSTER_MIN_SIMILARITY,
    MIN_CLUSTER_SIZE,
    cluster_evidence,
)
from core.storage.identity import Previo

AHORA = datetime(2026, 9, 1, tzinfo=UTC)


def item(n, texto, fuente="hackernews", horas=0):
    return EvidenceItem(id=f"{fuente}:{n}", source=fuente, community="c", kind="post", text=texto,
                        url=f"https://example.com/{n}", author_hash=None,
                        created_at=AHORA + timedelta(hours=horas), fetched_at=AHORA,
                        data_source="real")


FACTURAS = [
    item(1, "I export invoices by hand to a spreadsheet every month", horas=1),
    item(2, "Paso las facturas a mano a un Excel cada mes", "stackexchange", horas=2),
    item(3, "Exporting invoices manually for the accountant is painful", "github", horas=3),
]
ENVIOS = [
    item(4, "Shipping labels take forever, I copy addresses by hand", horas=4),
    item(5, "Las etiquetas de envío me llevan horas copiando direcciones", "stackexchange", horas=5),
    item(6, "Printing shipping labels one by one wastes my mornings", horas=6),
]
SUELTO = [item(7, "What is the best laptop for programming?", horas=7)]

VECTORES = {
    "hackernews:1": [1.0, 0.02, 0.0], "stackexchange:2": [0.98, 0.05, 0.0],
    "github:3": [0.97, 0.0, 0.05],
    "hackernews:4": [0.0, 1.0, 0.03], "stackexchange:5": [0.04, 0.99, 0.0],
    "hackernews:6": [0.0, 0.97, 0.06],
    "hackernews:7": [0.0, 0.0, 1.0],
}


class TestAgrupacion(unittest.TestCase):
    def test_constantes_con_nombre(self):
        self.assertEqual(MIN_CLUSTER_SIZE, 3)
        self.assertGreater(CLUSTER_MIN_SIMILARITY, 0.5)

    def test_agrupa_por_cercania_aunque_cambie_el_idioma(self):
        grupos = cluster_evidence(FACTURAS + ENVIOS + SUELTO, VECTORES)
        miembros = sorted(sorted(g.member_ids) for g in grupos)
        self.assertEqual(miembros, [
            ["github:3", "hackernews:1", "stackexchange:2"],
            ["hackernews:4", "hackernews:6", "stackexchange:5"],
        ])

    def test_lo_suelto_no_llega_al_juez(self):
        grupos = cluster_evidence(FACTURAS + ENVIOS + SUELTO, VECTORES)
        self.assertNotIn("hackernews:7", {m for g in grupos for m in g.member_ids})

    def test_es_determinista(self):
        a = cluster_evidence(FACTURAS + ENVIOS, VECTORES)
        b = cluster_evidence(list(reversed(FACTURAS + ENVIOS)), VECTORES)
        self.assertEqual([(g.key, sorted(g.member_ids)) for g in a],
                         [(g.key, sorted(g.member_ids)) for g in b])

    def test_palabras_clave_sin_palabras_vacias(self):
        [facturas] = [g for g in cluster_evidence(FACTURAS + ENVIOS, VECTORES)
                      if "hackernews:1" in g.member_ids]
        self.assertIn("invoices", facturas.keywords)
        for vacia in ("the", "to", "a", "las", "por"):
            self.assertNotIn(vacia, facturas.keywords)

    def test_palabras_clave_sin_restos_de_urls_contracciones_ni_relleno(self):
        """AUD2-006: los nichos reales se llamaban «email · notifications ·
        built/com/https/don/after/actually». Textos con la forma de los reales."""
        from core.judge.clustering import _palabras_clave

        palabras = _palabras_clave([
            "I've built a tool https://example.com/app for email alerts, don't miss it",
            "Actually, after I built it, where do you want email alerts? See www.foo.com/x",
            "Email alerts again: https://github.com/x/y (it doesn't work when the queue is full)",
        ])
        for resto in ("https", "com", "www", "github", "example", "don", "doesn", "built",
                      "actually", "after", "where", "want", "see", "again"):
            self.assertNotIn(resto, palabras)
        self.assertEqual(palabras[:2], ["alerts", "email"])

    def test_una_palabra_de_un_solo_texto_no_nombra_el_grupo(self):
        """AUD2-006 (causa raíz): en grupos de 3 a 10 piezas casi todo sale una
        vez y el desempate alfabético elegía «already · between»."""
        from core.judge.clustering import _palabras_clave

        palabras = _palabras_clave([
            "It already fails between retries: email alerts arrive late",
            "Email alerts never arrive for our domain",
            "Our domain email alerts are delayed",
        ])
        for suelta in ("already", "between", "fails", "retries", "late", "never", "delayed"):
            self.assertNotIn(suelta, palabras)
        self.assertEqual(set(palabras), {"alerts", "email", "domain", "arrive", "our"} & set(palabras))

    def test_singular_y_plural_cuentan_como_una(self):
        from core.judge.clustering import _palabras_clave

        palabras = _palabras_clave(["send invoices by email", "it sends invoice twice",
                                    "sends the invoices late"])
        self.assertFalse({"send", "sends"} <= set(palabras), palabras)
        self.assertFalse({"invoice", "invoices"} <= set(palabras), palabras)

    def test_lo_que_esta_en_todo_el_escaneo_no_distingue_al_grupo(self):
        from core.judge.clustering import _palabras_clave

        grupo = ["email bounces from our domain", "domain email bounces", "email to domain bounces"]
        otros = [f"email problem number {n}" for n in range(20)]
        palabras = _palabras_clave(grupo, fondo=grupo + otros)
        self.assertLess(palabras.index("domain"), palabras.index("email"))
        self.assertLess(palabras.index("bounces"), palabras.index("email"))

    def test_las_etiquetas_de_hacker_news_no_nombran_nichos(self):
        from core.judge.clustering import _palabras_clave

        palabras = _palabras_clave(["Show HN: invoice export tool", "Ask HN: invoice export pain",
                                    "Launch HN: Invoicer (YC W26) – invoice export"])
        for resto in ("show", "ask", "launch"):
            self.assertNotIn(resto, palabras)
        self.assertEqual(palabras[:2], ["export", "invoice"])

    def test_sin_vector_el_item_no_se_agrupa(self):
        vectores = {k: v for k, v in VECTORES.items() if k != "github:3"}
        grupos = cluster_evidence(FACTURAS, vectores)
        self.assertEqual(grupos, [], "con 2 miembros no llega al mínimo")


class TestIdentidad(unittest.TestCase):
    def test_hereda_el_uuid_de_una_lectura_anterior(self):
        previo = Previo(opportunity_id="11111111-1111-1111-1111-111111111111",
                        miembros={"hackernews:1", "stackexchange:2", "github:3"},
                        palabras={"invoices"})
        grupos = cluster_evidence(FACTURAS + ENVIOS, VECTORES, previous=[previo])
        por_miembro = {m: g.opportunity_id for g in grupos for m in g.member_ids}
        self.assertEqual(por_miembro["hackernews:1"], previo.opportunity_id)
        self.assertNotEqual(por_miembro["hackernews:4"], previo.opportunity_id)
        self.assertTrue(por_miembro["hackernews:4"])


if __name__ == "__main__":
    unittest.main()
