"""
Juez, etapas 3 y 4: dimensiones, compuertas y veredicto
=======================================================

Grupos construidos a mano (F3.7): uno que sale CONSTRUIR, uno INVESTIGAR MÁS
por cada compuerta que puede fallar, los DESCARTAR de la tabla D-M3 y el
test de honestidad (con 100 % demo nunca sale CONSTRUIR). Todo determinista:
el juez solo cuenta etiquetas verificadas; lo `undetermined` nunca suma.
"""

import unittest
from datetime import UTC, datetime, timedelta

from core.evidence.model import EvidenceItem
from core.judge.dimensions import WEIGHTS, WEIGHTS_VERSION, score_cluster
from core.judge.gates import (
    CONCENTRATION_MAX_SHARE,
    MIN_DISTINCT_AUTHORS,
    MIN_DISTINCT_SOURCES,
    RECENCY_DAYS,
    RECENCY_MIN_SHARE,
    judge_cluster,
)
from core.judge.labels import VerifiedCompetitor, VerifiedLabel
from tests._ayudas import presente

AHORA = datetime(2026, 9, 1, tzinfo=UTC)
FUENTES = ("hackernews", "stackexchange", "github")


def pieza(n, *, fuente=None, autor=None, hilo=None, dias=10, procedencia="real"):
    fuente = fuente or FUENTES[n % 3]
    return EvidenceItem(
        id=f"{fuente}:{n}", source=fuente, community="c", kind="post", text=f"queja {n}",
        url=f"https://example.com/{n}", author_hash=autor if autor is not None else f"{n:064x}",
        created_at=AHORA - timedelta(days=dias), fetched_at=AHORA,
        thread_id=f"{fuente}:{hilo if hilo is not None else n}", data_source=procedencia)


def etiqueta(item_id, *, dolor="yes", intent="queja", parche="no", pago="no", competidores=()):
    return VerifiedLabel(item_id=item_id, content_hash="h", labeler="t", is_pain=dolor,
                         intent=intent, workaround_described=parche, wtp_signal=pago,
                         competitors=list(competidores))


def grupo_construir(n=10, **cambios):
    """10 dolores de 3 fuentes y 10 autores, recientes, con parche y pago."""
    items = [pieza(i, **cambios) for i in range(n)]
    etiquetas = {i.id: etiqueta(i.id) for i in items}
    etiquetas[items[0].id] = etiqueta(items[0].id, intent="parche_casero", parche="yes")
    etiquetas[items[1].id] = etiqueta(items[1].id, intent="dispuesto_a_pagar", pago="yes")
    return items, etiquetas


class TestConstantes(unittest.TestCase):
    def test_umbrales_de_la_mision(self):
        self.assertEqual((MIN_DISTINCT_SOURCES, MIN_DISTINCT_AUTHORS), (2, 8))
        self.assertEqual((CONCENTRATION_MAX_SHARE, RECENCY_DAYS, RECENCY_MIN_SHARE), (0.40, 180, 0.50))

    def test_pesos_versionados_de_d_m3(self):
        self.assertEqual(WEIGHTS, {"frecuencia": 0.25, "pago": 0.25, "parches": 0.20,
                                   "hueco": 0.15, "tendencia": 0.15})
        self.assertAlmostEqual(sum(WEIGHTS.values()), 1.0)
        self.assertTrue(WEIGHTS_VERSION)


class TestVeredictos(unittest.TestCase):
    def veredicto(self, items, etiquetas):
        return judge_cluster(items, etiquetas, now=AHORA)

    def test_todo_pasa_construir(self):
        resultado = self.veredicto(*grupo_construir())
        self.assertEqual(resultado.verdict, "CONSTRUIR")
        self.assertEqual(resultado.missing, [])
        self.assertTrue(all(g.passed for g in resultado.gates))

    def test_cada_compuerta_guarda_valor_umbral_y_evidencia(self):
        resultado = self.veredicto(*grupo_construir())
        g2 = next(g for g in resultado.gates if g.gate == "G2")
        self.assertEqual((g2.value, g2.threshold), (10, 8))
        self.assertEqual(len(g2.evidence_ids), 10)
        self.assertEqual([g.gate for g in resultado.gates], [f"G{n}" for n in range(1, 9)])

    def test_g1_una_sola_fuente_investigar(self):
        resultado = self.veredicto(*grupo_construir(fuente="hackernews"))
        self.assertEqual((resultado.verdict, resultado.missing), ("INVESTIGAR MÁS", ["G1"]))

    def test_g2_pocos_autores_pero_al_menos_la_mitad_investigar(self):
        items, etiquetas = grupo_construir()
        items = [i.model_copy(update={"author_hash": f"{n % 5:064x}"}) for n, i in enumerate(items)]
        resultado = self.veredicto(items, etiquetas)
        self.assertEqual(resultado.verdict, "INVESTIGAR MÁS")
        self.assertIn("G2", resultado.missing)

    def test_g3_sin_parche_investigar(self):
        items, etiquetas = grupo_construir()
        etiquetas[items[0].id] = etiqueta(items[0].id)
        resultado = self.veredicto(items, etiquetas)
        self.assertEqual((resultado.verdict, resultado.missing), ("INVESTIGAR MÁS", ["G3"]))

    def test_g4_sin_pago_ni_busqueda_investigar(self):
        items, etiquetas = grupo_construir()
        etiquetas[items[1].id] = etiqueta(items[1].id)
        resultado = self.veredicto(items, etiquetas)
        self.assertEqual((resultado.verdict, resultado.missing), ("INVESTIGAR MÁS", ["G4"]))

    def test_g4_tambien_vale_quien_busca_herramienta(self):
        items, etiquetas = grupo_construir()
        etiquetas[items[1].id] = etiqueta(items[1].id, intent="busca_herramienta")
        self.assertEqual(self.veredicto(items, etiquetas).verdict, "CONSTRUIR")

    def test_g5_un_hilo_concentra_la_evidencia_investigar(self):
        items, etiquetas = grupo_construir()
        items = [i.model_copy(update={"thread_id": "hackernews:hilo"}) if n < 5 else i
                 for n, i in enumerate(items)]
        resultado = self.veredicto(items, etiquetas)
        self.assertEqual((resultado.verdict, resultado.missing), ("INVESTIGAR MÁS", ["G5"]))

    def test_g5_sin_hilo_conocido_no_cuenta_como_un_mismo_hilo(self):
        items, etiquetas = grupo_construir()
        items = [i.model_copy(update={"thread_id": None}) for i in items]
        g5 = next(g for g in self.veredicto(items, etiquetas).gates if g.gate == "G5")
        self.assertTrue(g5.passed, "hilo desconocido no es concentración")

    def test_g6_evidencia_vieja_investigar(self):
        resultado = self.veredicto(*grupo_construir(dias=400))
        self.assertEqual(resultado.verdict, "INVESTIGAR MÁS")
        self.assertIn("G6", resultado.missing)

    def test_g8_datos_demo_como_mucho_investigar(self):
        resultado = self.veredicto(*grupo_construir(procedencia="demo"))
        self.assertEqual((resultado.verdict, resultado.missing), ("INVESTIGAR MÁS", ["G8"]))

    def test_honestidad_100_por_cien_demo_nunca_construir(self):
        # Test de honestidad de la misión: ni con todo lo demás perfecto.
        for n in (8, 10, 30, 60):
            with self.subTest(miembros=n):
                items, etiquetas = grupo_construir(n=n, procedencia="demo")
                self.assertNotEqual(self.veredicto(items, etiquetas).verdict, "CONSTRUIR")

    def test_legacy_sin_procedencia_tampoco_es_real(self):
        items, etiquetas = grupo_construir()
        items[0] = items[0].model_copy(update={"data_source": None})
        self.assertIn("G8", self.veredicto(items, etiquetas).missing)

    def test_g7_competidor_gratuito_satisfactorio_descartar(self):
        items, etiquetas = grupo_construir()
        gratis = VerifiedCompetitor(name="TallyBird", stance="satisfecho", free=True,
                                    evidence_span="TallyBird")
        for i in items[2:5]:
            etiquetas[i.id] = etiqueta(i.id, dolor="no", intent="mencion_competidor",
                                       competidores=[gratis])
        resultado = self.veredicto(items, etiquetas)
        self.assertEqual(resultado.verdict, "DESCARTAR")
        self.assertIn("G7", resultado.missing)

    def _g7_favorable(self, autores):
        """Menciones favorables de un competidor gratuito por las piezas 2, 3…,
        con los autores dados (uno por pieza)."""
        items, etiquetas = grupo_construir()
        gratis = VerifiedCompetitor(name="TallyBird", stance="satisfecho", free=True,
                                    evidence_span="TallyBird")
        for n, autor in enumerate(autores, start=2):
            items[n] = items[n].model_copy(update={"author_hash": autor})
            etiquetas[items[n].id] = etiqueta(items[n].id, dolor="no", intent="mencion_competidor",
                                              competidores=[gratis])
        return items, self.veredicto(items, etiquetas)

    def test_g7_un_autor_favorable_no_descarta_pero_no_construye(self):
        # Impagos (E8): un solo lanzamiento de HN decidía G7 al 100 % y DESCARTAR.
        # Regla aprobada: un competidor cuenta con al menos 3 autores distintos.
        items, resultado = self._g7_favorable([f"{900:064x}"])
        g7 = next(g for g in resultado.gates if g.gate == "G7")
        self.assertEqual((g7.passed, g7.measured, g7.evidence_ids), (True, False, [items[2].id]))
        self.assertIn("TallyBird", g7.note or "")
        self.assertEqual(resultado.verdict, "INVESTIGAR MÁS")
        self.assertTrue(resultado.rule.startswith("9:"), resultado.rule)

    def test_g7_dos_piezas_del_mismo_autor_son_un_autor(self):
        _, resultado = self._g7_favorable([f"{900:064x}", f"{900:064x}", f"{901:064x}"])
        self.assertEqual(resultado.verdict, "INVESTIGAR MÁS", "2 autores: aún no cuenta")

    def test_g7_tres_autores_con_mayoria_favorable_descarta(self):
        _, resultado = self._g7_favorable([f"{900 + n:064x}" for n in range(3)])
        self.assertEqual((resultado.verdict, resultado.rule), ("DESCARTAR", "1: falla G7"))

    def test_g2_menos_de_la_mitad_de_autores_descartar(self):
        items, etiquetas = grupo_construir()
        items = [i.model_copy(update={"author_hash": f"{n % 3:064x}"}) for n, i in enumerate(items)]
        self.assertEqual(self.veredicto(items, etiquetas).verdict, "DESCARTAR")

    def test_g1_y_g2_a_la_vez_descartar(self):
        items, etiquetas = grupo_construir(fuente="hackernews")
        items = [i.model_copy(update={"author_hash": f"{n % 6:064x}"}) for n, i in enumerate(items)]
        resultado = self.veredicto(items, etiquetas)
        self.assertEqual(resultado.verdict, "DESCARTAR")

    def test_lo_undetermined_nunca_suma(self):
        items, etiquetas = grupo_construir()
        etiquetas = {k: v.model_copy(update={"is_pain": "undetermined"}) for k, v in etiquetas.items()}
        resultado = self.veredicto(items, etiquetas)
        self.assertEqual(resultado.verdict, "DESCARTAR")
        self.assertEqual(next(g for g in resultado.gates if g.gate == "G2").value, 0)


class TestPuntaje(unittest.TestCase):
    def test_puntaje_d_m3_y_version(self):
        items, etiquetas = grupo_construir()
        puntaje = score_cluster(items, etiquetas, now=AHORA)
        self.assertEqual(puntaje.weights_version, WEIGHTS_VERSION)
        dims = {d.name: d for d in puntaje.dimensions}
        self.assertEqual(dims["frecuencia"].value, 10)
        self.assertAlmostEqual(presente(dims["frecuencia"].normalized), 10 / 30)
        self.assertEqual(dims["convergencia"].value, 3)
        self.assertEqual(dims["viabilidad"].normalized, None, "undetermined en F3")
        base = (0.25 * 10 / 30 + 0.25 * 1 / 5 + 0.20 * 1 / 5 + 0.15 * presente(dims["hueco"].normalized)
                + 0.15 * presente(dims["tendencia"].normalized))
        self.assertAlmostEqual(puntaje.score, 100 * base * (0.5 + 0.5 * 1.0))

    def test_cada_dimension_lista_sus_items(self):
        items, etiquetas = grupo_construir()
        dims = {d.name: d for d in score_cluster(items, etiquetas, now=AHORA).dimensions}
        self.assertEqual(dims["parches"].item_ids, [items[0].id])
        self.assertEqual(dims["pago"].item_ids, [items[1].id])

    def test_sin_competidores_el_hueco_es_neutro_y_se_dice(self):
        items, etiquetas = grupo_construir()
        hueco = next(d for d in score_cluster(items, etiquetas, now=AHORA).dimensions
                     if d.name == "hueco")
        self.assertEqual((hueco.normalized, hueco.note), (0.5, "sin_datos"))


if __name__ == "__main__":
    unittest.main()
