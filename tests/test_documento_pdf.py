"""
Documento genérico: PDF y Markdown desde el mismo modelo (E1, E7)
=================================================================

El dossier y el plan de la Fase E se componen como un `DocumentModel` y se
pintan igual: PDF A4 con portada, índice con páginas reales, encabezado y
pie en todas las páginas, franja «no recomendado» en cada página si el plan
se forzó, y marca de agua solo con datos de demostración. El texto se lee
con pypdf, como lo leería quien abre el documento: tildes, ñ, ¿, ¡, «» y —
tienen que salir intactos.
"""

import io
import re
import unittest
from dataclasses import replace
from typing import Any

from pypdf import PdfReader

from core.documents.model import Block, DocumentModel, Section
from core.documents.pdf_report import render_pdf
from tests._ayudas import presente

TITULO = "Dossier · Facturación manual: ¿por qué falla? ¡Ñandú!"
FRANJA = "El juez no recomienda construir este nicho: 5: fallan G1, G2 o G5"


def documento(**cambios: Any) -> DocumentModel:
    base = DocumentModel(
        language="es", kind="dossier", title=TITULO, data_source="real",
        cover=(("Veredicto", "CONSTRUIR"), ("Ejecución", "run-1")),
        source_notice="Datos reales de 3 fuentes con API oficial.",
        sections=(
            Section("resumen", "1. Resumen del veredicto", (
                Block("paragraph", "Año tras año, la conciliación «a mano» cuesta — y mucho…"),
                Block("table", rows=(("Puntuación", "61,5"), ("Regla", "7: pasan todas"))),
            )),
            Section("problema", "2. El problema", (
                Block("bullets", items=("Exportar facturas lleva horas [hackernews:1]",)),
                Block("note", "1 afirmación retirada por citar evidencia inexistente."),
            )),
            Section("pasos", "3. Pasos", tuple(
                b for n in range(1, 13) for b in (
                    Block("subheading", f"Paso {n}: objetivo número {n}"),
                    Block("code", "npm test\npython -m unittest"),
                    Block("table", rows=(("Hecho cuando", "los tests pasan"),)),
                )
            )),
        ),
    )
    return replace(base, **cambios)


def paginas(pdf: bytes) -> list[str]:
    return [p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages]


class TestPdf(unittest.TestCase):
    def test_es_un_pdf_con_portada_indice_y_secciones_en_orden(self):
        pdf = render_pdf(documento())
        self.assertTrue(pdf.startswith(b"%PDF"))
        texto = "\n".join(paginas(pdf))
        posiciones = [texto.index(t, texto.index("Índice")) for t in
                      ("1. Resumen del veredicto", "2. El problema", "3. Pasos")]
        self.assertEqual(posiciones, sorted(posiciones))

    def test_el_indice_lleva_numeros_de_pagina_reales(self):
        hojas = paginas(render_pdf(documento()))
        indice = next(h for h in hojas if "Índice" in h)
        numero = int(presente(re.search(r"3\. Pasos\D*(\d+)", indice)).group(1))
        self.assertIn("3. Pasos", hojas[numero - 1])

    def test_tildes_enes_y_signos_se_leen_intactos(self):
        texto = "\n".join(paginas(render_pdf(documento())))
        for fragmento in ("¿por qué falla?", "¡Ñandú!", "«a mano»", "— y mucho…", "Año tras año"):
            self.assertIn(fragmento, texto)

    def test_encabezado_y_pie_en_todas_las_paginas(self):
        hojas = paginas(render_pdf(documento()))
        self.assertGreater(len(hojas), 2)
        for n, hoja in enumerate(hojas, start=1):
            self.assertIn(f"página {n} de {len(hojas)}", hoja)
            self.assertIn("SENTRA", hoja)

    def test_marca_de_agua_solo_con_datos_de_demostracion(self):
        for hoja in paginas(render_pdf(documento(data_source="demo"))):
            self.assertIn("DATOS DE DEMOSTRACIÓN", hoja)
        for hoja in paginas(render_pdf(documento(data_source="real"))):
            self.assertNotIn("DATOS DE DEMOSTRACIÓN", hoja)

    def test_la_franja_de_no_recomendado_va_en_cada_pagina(self):
        for hoja in paginas(render_pdf(documento(kind="plan", stripe=FRANJA))):
            self.assertIn("El juez no recomienda construir este nicho", hoja)
        for hoja in paginas(render_pdf(documento(kind="plan"))):
            self.assertNotIn("no recomienda", hoja)

    def test_en_ingles_los_rotulos_en_ingles(self):
        hojas = paginas(render_pdf(documento(language="en", data_source="demo")))
        self.assertIn("Contents", hojas[1])
        self.assertIn(f"page 1 of {len(hojas)}", hojas[0])
        self.assertIn("DEMO DATA", hojas[0])


class TestMarkdown(unittest.TestCase):
    def test_estructura_para_un_agente(self):
        md = documento().to_markdown()
        lineas = md.splitlines()
        self.assertEqual(lineas[0], "> Datos reales de 3 fuentes con API oficial.")
        self.assertIn(f"# {TITULO}", lineas)
        self.assertEqual([l for l in lineas if l.startswith("## ")],
                         ["## 1. Resumen del veredicto", "## 2. El problema", "## 3. Pasos"])
        self.assertIn("### Paso 10: objetivo número 10", lineas)
        self.assertIn("```\nnpm test\npython -m unittest\n```", md)
        self.assertIn("| Puntuación | 61,5 |", lineas)
        self.assertIn("- Exportar facturas lleva horas [hackernews:1]", lineas)

    def test_la_franja_encabeza_el_documento_y_cada_seccion(self):
        md = documento(kind="plan", stripe=FRANJA).to_markdown()
        self.assertTrue(md.startswith(f"> **{FRANJA}**"))
        self.assertEqual(md.count(FRANJA), 1 + 3)

    def test_con_demostracion_lo_dice_el_markdown(self):
        md = documento(data_source="demo").to_markdown()
        self.assertIn("DATOS DE DEMOSTRACIÓN", md.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
