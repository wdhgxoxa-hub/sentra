"""
Un lanzamiento propio no es un dolor (AUD2-001, 6.1)
===================================================

En los veredictos reales, «Show HN: I built X» contaba como parche casero
(G3 = 6 en un grupo de lanzamientos sin relación). Anunciar lo que uno ha
construido no es un problema del mercado ni una forma de apañárselas con
él, ni una señal de pago, aunque el etiquetador lo marque así: el código no
lo cuenta. Sigue en la evidencia (puede nombrar competidores para G7).
"""

import unittest

from core.judge.dimensions import (
    es_lanzamiento,
    pain_items,
    payment_items,
    workaround_items,
)
from tests.test_judge_verdict import etiqueta, pieza


def lanzamiento(n, titulo):
    return pieza(n).model_copy(update={"title": titulo, "text": "I built this to send email alerts"})


class TestPertinencia(unittest.TestCase):
    def test_un_lanzamiento_no_cuenta_como_dolor_parche_ni_pago(self):
        show = lanzamiento(1, "Show HN: AgentMailr – inboxes for AI agents")
        queja = pieza(2)
        etiquetas = {i.id: etiqueta(i.id, intent="parche_casero", parche="yes", pago="yes")
                     for i in (show, queja)}
        for contar in (pain_items, workaround_items, payment_items):
            self.assertEqual([i.id for i in contar([show, queja], etiquetas)], [queja.id], contar.__name__)

    def test_que_es_un_lanzamiento(self):
        for titulo in ("Show HN: X", "show hn: x", "Launch HN: Acme (YC W26)", "  Show HN — X"):
            self.assertTrue(es_lanzamiento(lanzamiento(1, titulo)), titulo)
        no_lanzamientos: tuple[str | None, ...] = (
            None, "Ask HN: how do you handle email bounces?", "Showing HN results", "I hate my invoicing tool")
        for otro in no_lanzamientos:
            self.assertFalse(es_lanzamiento(lanzamiento(1, otro)), otro)

    def test_un_anuncio_en_el_texto_tampoco_cuenta_como_dolor(self):
        # Sin título de lanzamiento: el anuncio va en el texto (Bluesky, Mastodon).
        anuncio = pieza(3).model_copy(update={"text": (
            "Following up on late invoices manually is tedious. The fix: an automatic reminder sequence "
            "that stops the moment the client pays.")})
        queja = pieza(4)
        etiquetas = {i.id: etiqueta(i.id, intent="parche_casero", parche="yes", pago="yes")
                     for i in (anuncio, queja)}
        for contar in (pain_items, workaround_items, payment_items):
            self.assertEqual([i.id for i in contar([anuncio, queja], etiquetas)], [queja.id], contar.__name__)


if __name__ == "__main__":
    unittest.main()
