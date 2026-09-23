"""
Juez, etapa 0: filtro de calidad determinista
=============================================

Cada ítem descartado lleva su motivo. La autopromoción («I built X») no se
descarta: no cuenta como dolor, pero se conserva como señal de competencia.
Textos inventados (R8).
"""

import unittest
from datetime import UTC, datetime

from core.evidence.model import EvidenceItem
from core.judge.quality import (
    MIN_CHARS,
    MIN_WORDS,
    SUPPORTED_LANGUAGES,
    QualityVerdict,
    filter_quality,
    judge_quality,
)

AHORA = datetime(2026, 9, 1, tzinfo=UTC)


def item(texto, idioma=None, n=1):
    return EvidenceItem(id=f"hackernews:{n}", source="hackernews", community="Ask HN", kind="post",
                        text=texto, url=f"https://example.com/{n}", author_hash=None,
                        created_at=AHORA, fetched_at=AHORA, language=idioma, data_source="real")


DOLOR = "I export every invoice by hand into a spreadsheet and it takes hours each month."


class TestMotivos(unittest.TestCase):
    def test_un_dolor_normal_pasa_sin_motivo(self):
        self.assertEqual(judge_quality(item(DOLOR)), QualityVerdict("hackernews:1", True, None, False))

    def test_demasiado_corto(self):
        for texto in ("+1", "same here", "a" * (MIN_CHARS - 1)):
            with self.subTest(texto=texto):
                veredicto = judge_quality(item(texto))
                self.assertEqual((veredicto.keep, veredicto.reason), (False, "too_short"))
        self.assertEqual(MIN_WORDS, 4)

    def test_idioma_no_soportado_solo_si_esta_declarado(self):
        self.assertEqual(SUPPORTED_LANGUAGES, frozenset({"en", "es"}))
        self.assertEqual(judge_quality(item(DOLOR, idioma="de")).reason, "unsupported_language")
        self.assertTrue(judge_quality(item(DOLOR, idioma=None)).keep)
        self.assertTrue(judge_quality(item(DOLOR, idioma="es")).keep)
        self.assertTrue(judge_quality(item(DOLOR, idioma="en-US")).keep, "variantes regionales")

    def test_spam_de_enlaces(self):
        texto = "Best deals https://a.example https://b.example https://c.example buy now today"
        self.assertEqual(judge_quality(item(texto)).reason, "spam")

    def test_afiliados(self):
        for texto in ("Great tool for invoices, sign up with my link https://x.example/?ref=abc123 please",
                      "Usa el código de descuento FACTURA20 para ahorrar en tu facturación mensual"):
            with self.subTest(texto=texto):
                self.assertEqual(judge_quality(item(texto)).reason, "affiliate")

    def test_bots(self):
        texto = "I am a bot, and this action was performed automatically. Please contact the moderators."
        self.assertEqual(judge_quality(item(texto)).reason, "bot")
        otro = "beep boop, here is the summary of this thread you asked for yesterday"
        self.assertEqual(judge_quality(item(otro)).reason, "bot")

    def test_autopromocion_se_conserva_como_competencia(self):
        for texto in ("I built a tool that exports invoices to CSV automatically, feedback welcome",
                      "He creado una app que concilia facturas con el banco en un clic, ¿qué os parece?"):
            with self.subTest(texto=texto):
                veredicto = judge_quality(item(texto))
                self.assertEqual((veredicto.keep, veredicto.reason, veredicto.competition_signal),
                                 (True, "self_promotion", True))


class TestLote(unittest.TestCase):
    def test_separa_lo_que_pasa_y_registra_cada_descarte(self):
        items = [item(DOLOR, n=1), item("+1", n=2), item("I built an invoice exporter for freelancers", n=3)]
        resultado = filter_quality(items)
        self.assertEqual([i.id for i in resultado.kept], ["hackernews:1", "hackernews:3"])
        self.assertEqual({v.item_id: v.reason for v in resultado.discarded}, {"hackernews:2": "too_short"})
        self.assertEqual([v.item_id for v in resultado.competition], ["hackernews:3"])


if __name__ == "__main__":
    unittest.main()
