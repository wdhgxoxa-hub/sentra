"""
Esquema común de evidencia y autores anónimos (F2.1, F2.2, R9)
==============================================================

Toda fuente entrega `EvidenceItem`: id global `<fuente>:<id_nativo>`, URL
canónica al original, fechas en UTC, procedencia (`real` o `demo`) y el
autor SOLO como hash salado. El nombre de usuario no se guarda nunca: el
hash existe para contar autores distintos (compuerta G2), no para saber
quién es nadie.
"""

import shutil
import tempfile
import unittest
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from core.evidence.author import AUTHOR_SALT_ENV, author_hash, load_or_create_salt
from core.evidence.model import Engagement, EvidenceItem, SearchQuery
from tests._ayudas import presente

SAL = "0f" * 32
AHORA = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def item(**cambios):
    base: dict[str, Any] = {
        "id": "hackernews:123",
        "source": "hackernews",
        "community": "Ask HN",
        "kind": "post",
        "title": "Ask HN: how do you reconcile invoices?",
        "text": "I spend hours every week matching invoices by hand.",
        "url": "https://news.ycombinator.com/item?id=123",
        "author_hash": author_hash("hackernews", "alguien", SAL),
        "created_at": AHORA,
        "fetched_at": AHORA,
        "language": "en",
        "thread_id": "hackernews:123",
        "engagement": Engagement(score=42, replies=7),
        "native_metrics": {"points": 42},
        "data_source": "real",
        "run_id": None,
    }
    base.update(cambios)
    return EvidenceItem(**base)


class TestHashDeAutor(unittest.TestCase):
    def test_es_un_hash_hex_sin_rastro_del_nombre(self):
        h = presente(author_hash("reddit", "Ana_Lopez", SAL))
        self.assertRegex(h, r"^[0-9a-f]{64}$")
        self.assertNotIn("ana_lopez", h.lower())

    def test_es_estable_e_ignora_mayusculas(self):
        self.assertEqual(author_hash("reddit", "Ana", SAL), author_hash("reddit", "ana", SAL))

    def test_depende_de_la_sal_y_de_la_fuente(self):
        base = author_hash("reddit", "ana", SAL)
        self.assertNotEqual(base, author_hash("reddit", "ana", "aa" * 32))
        # Sin evidencia de que sean la misma persona, no se funden entre plataformas.
        self.assertNotEqual(base, author_hash("github", "ana", SAL))

    def test_sin_autor_o_borrado_no_hay_hash(self):
        for vacio in (None, "", "  ", "[deleted]", "[removed]"):
            with self.subTest(autor=vacio):
                self.assertIsNone(author_hash("reddit", vacio, SAL))


class TestSal(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rir_sal_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = self.tmp / ".env"
        self.env.write_text("OTRA=1\n", encoding="utf-8")

    def test_se_genera_una_vez_y_se_reutiliza(self):
        primera = load_or_create_salt(str(self.env))
        segunda = load_or_create_salt(str(self.env))
        self.assertEqual(primera, segunda)
        self.assertRegex(primera, r"^[0-9a-f]{64}$")
        contenido = self.env.read_text(encoding="utf-8")
        self.assertEqual(contenido.count(f"{AUTHOR_SALT_ENV}="), 1)
        self.assertIn("OTRA=1", contenido)

    def test_dos_instalaciones_no_comparten_sal(self):
        otro = self.tmp / "otro.env"
        self.assertNotEqual(load_or_create_salt(str(self.env)), load_or_create_salt(str(otro)))


class TestEvidenceItem(unittest.TestCase):
    def test_un_item_valido(self):
        self.assertEqual(item().id, "hackernews:123")

    def test_el_id_global_empieza_por_su_fuente(self):
        with self.assertRaises(ValidationError):
            item(id="reddit:123")
        with self.assertRaises(ValidationError):
            item(id="123")

    def test_las_fechas_sin_zona_se_rechazan_y_las_demas_pasan_a_utc(self):
        with self.assertRaises(ValidationError):
            item(created_at=datetime(2026, 9, 1, 12, 0))  # noqa: DTZ001 - ingenua a propósito: debe rechazarse
        lima = timezone(timedelta(hours=-5))
        convertido = item(created_at=datetime(2026, 9, 1, 7, 0, tzinfo=lima))
        self.assertEqual(convertido.created_at, AHORA)
        self.assertEqual(convertido.created_at.tzinfo, UTC)

    def test_la_url_es_https_al_original(self):
        with self.assertRaises(ValidationError):
            item(url="javascript:alert(1)")
        with self.assertRaises(ValidationError):
            item(url="")

    def test_el_autor_solo_como_hash(self):
        with self.assertRaises(ValidationError):
            item(author_hash="ana_lopez")
        self.assertIsNone(item(author_hash=None).author_hash)

    def test_procedencia_real_o_demo(self):
        with self.assertRaises(ValidationError):
            item(data_source="reddit")

    def test_el_texto_no_puede_estar_vacio(self):
        with self.assertRaises(ValidationError):
            item(text="   ")


class TestSearchQuery(unittest.TestCase):
    def test_modo_tema_y_modo_descubrimiento(self):
        tema = SearchQuery(keywords=["invoicing"], phrases=["is there a tool"])
        self.assertFalse(tema.discovery)
        descubrir = SearchQuery(keywords=[], phrases=["I hate"], discovery=True)
        self.assertTrue(descubrir.discovery)

    def test_sin_tema_hay_que_pedir_descubrimiento_explicitamente(self):
        with self.assertRaises(ValidationError):
            SearchQuery(keywords=[], phrases=["I hate"])

    def test_los_terminos_se_limpian(self):
        q = SearchQuery(keywords=["  invoicing ", ""], phrases=["x"])
        self.assertEqual(q.keywords, ["invoicing"])


if __name__ == "__main__":
    unittest.main()

