"""
Atribución de la evidencia (R5, términos de Stack Exchange)
===========================================================

Los términos de la API de Stack Exchange exigen indicar visualmente que la
red Stack Exchange es la fuente; en aplicaciones sin navegador basta la URL
en texto plano. SENTRA lo aplica a todas las fuentes (R5): insignia de la
plataforma, sitio o comunidad y URL del original, siempre las tres.
"""

import unittest
from datetime import UTC, datetime

from core.evidence.model import EvidenceItem
from core.sources.attribution import attribution, attribution_line

AHORA = datetime(2026, 9, 1, tzinfo=UTC)


def item(fuente, comunidad, url):
    return EvidenceItem(id=f"{fuente}:1", source=fuente, community=comunidad, kind="question",
                        text="texto inventado", url=url, author_hash=None, created_at=AHORA,
                        fetched_at=AHORA, data_source="real")


class TestAtribucion(unittest.TestCase):
    def test_stack_exchange_lleva_insignia_sitio_y_url_en_texto_plano(self):
        pregunta = item("stackexchange", "Stack Overflow",
                        "https://stackoverflow.com/questions/79000001/x")
        self.assertEqual(attribution(pregunta), {
            "badge": "Stack Exchange", "site": "Stack Overflow",
            "url": "https://stackoverflow.com/questions/79000001/x"})
        self.assertEqual(attribution_line(pregunta),
                         "Stack Exchange · Stack Overflow · https://stackoverflow.com/questions/79000001/x")

    def test_todas_las_fuentes_del_catalogo_se_atribuyen(self):
        from core.sources.catalog import SOURCES

        for clase in SOURCES:
            with self.subTest(fuente=clase.id):
                datos = attribution(item(clase.id, "comunidad", "https://example.com/1"))
                self.assertEqual(datos["badge"], clase.display_name)
                self.assertTrue(all(datos.values()))

    def test_una_fuente_fuera_del_catalogo_no_se_queda_sin_insignia(self):
        self.assertEqual(attribution(item("demo", "c", "https://example.com/1"))["badge"], "demo")


if __name__ == "__main__":
    unittest.main()
