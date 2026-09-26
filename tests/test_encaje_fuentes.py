"""
Fuentes según el tipo de tema (Fase 3, medida B de Walter)
==========================================================

Escaneo 2 («perseguir a los clientes para que manden sus documentos al
contable»): Stack Exchange buscó en Stack Overflow y GitHub en issues de
software; 50 de las 53 quejas eran fallos de programación. Regla:

- GitHub solo entra en temas de software.
- Stack Exchange busca en los sitios adecuados al tema, de un catálogo
  cerrado; sin ninguno adecuado, no se consulta.
- Lo que no encaja se omite en ese escaneo y se dice (motivo).
- Sin saber el tipo (sin Gemini, o en descubrimiento) no se omite nada.
"""

import unittest
from typing import Any

from pydantic import ValidationError

from core.sources.encaje import NO_ES_SOFTWARE, SIN_SITIO, fuentes_omitidas
from core.sources.profile import ScanProfile
from core.sources.stackexchange import SITIOS

TODAS = ("hackernews", "stackexchange", "github", "bluesky", "youtube", "mastodon", "discourse", "producthunt")


def perfil(**cambios: Any) -> ScanProfile:
    base: dict[str, Any] = {"name": "Perseguir documentos", "keywords": ["documentos contabilidad"],
            "topic": "Perseguir a los clientes para que manden sus documentos al contable"}
    base.update(cambios)
    return ScanProfile(**base)


class TestPerfil(unittest.TestCase):
    def test_lleva_el_tema_completo_y_su_tipo(self):
        p = perfil(topic_kind="otro", targets={"stackexchange": ["money"]})
        self.assertEqual(p.topic, "Perseguir a los clientes para que manden sus documentos al contable")
        self.assertEqual(p.topic_kind, "otro")

    def test_sin_tipo_por_defecto(self):
        self.assertIsNone(perfil().topic_kind)

    def test_solo_sitios_del_catalogo(self):
        with self.assertRaises(ValidationError):
            perfil(targets={"stackexchange": ["sitio-inventado"]})
        perfil(targets={"stackexchange": ["money", "freelancing:invoicing"]})

    def test_el_catalogo_tiene_sitios_de_negocio(self):
        for sitio in ("money", "freelancing", "workplace", "pm", "law", "stackoverflow", "superuser"):
            self.assertIn(sitio, SITIOS)


class TestFuentesOmitidas(unittest.TestCase):
    def test_tema_que_no_es_de_software_sin_sitios(self):
        self.assertEqual(fuentes_omitidas(perfil(topic_kind="otro"), TODAS),
                         {"github": NO_ES_SOFTWARE, "stackexchange": SIN_SITIO})

    def test_tema_que_no_es_de_software_con_sitio_adecuado(self):
        self.assertEqual(fuentes_omitidas(perfil(topic_kind="otro", targets={"stackexchange": ["money"]}), TODAS),
                         {"github": NO_ES_SOFTWARE})

    def test_tema_de_software(self):
        self.assertEqual(fuentes_omitidas(perfil(topic_kind="software",
                                                 targets={"stackexchange": ["stackoverflow"]}), TODAS), {})

    def test_sin_saber_el_tipo_no_se_omite_nada(self):
        self.assertEqual(fuentes_omitidas(perfil(), TODAS), {})

    def test_en_descubrimiento_no_se_omite_nada(self):
        descubrir = ScanProfile(name="d", discovery=True, topic_kind="otro")
        self.assertEqual(fuentes_omitidas(descubrir, TODAS), {})

    def test_solo_de_las_fuentes_que_hay(self):
        self.assertEqual(fuentes_omitidas(perfil(topic_kind="otro"), ("hackernews", "github")),
                         {"github": NO_ES_SOFTWARE})

    def test_los_motivos_se_guardan_como_motivo_de_parada(self):
        self.assertTrue(NO_ES_SOFTWARE.startswith("omitida:"))
        self.assertTrue(SIN_SITIO.startswith("omitida:"))


if __name__ == "__main__":
    unittest.main()
