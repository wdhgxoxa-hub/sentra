"""
Exportación del documento a PDF (AUD-008)
=========================================

El PDF se genera en el sidecar con ReportLab y se valida aquí leyéndolo con
pypdf (dependencia solo de pruebas, requirements-dev.txt): se extrae el texto
de verdad, así que un carácter mal incrustado o una sección fuera de sitio se
detectan igual que los vería quien abre el documento.
"""

import io
import logging
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfReader

from core.documents.pdf_report import build_pdf
from core.ingestion.synthetic import SyntheticFetcher
from core.orchestration import RadarDependencies
from core.orchestration.sidecar_server import create_app
from core.storage import HashEmbedder, HybridSearchEngine, LanceDBStore

ETIQUETA = "Facturación manual: ¿por qué falla? ¡Otra vez! Ñandú"

SECCIONES_ES = [
    "1. Resumen ejecutivo",
    "2. Problema",
    "3. Evidencia",
    "4. Usuario objetivo y JTBD",
    "5. Solución propuesta",
    "6. Alcance del MVP",
    "7. Plan de arquitectura",
    "8. Riesgos y fallos conocidos",
    "9. Modelo de negocio",
    "10. Metadatos y trazabilidad",
]
SECCIONES_EN = [
    "1. Executive summary",
    "2. Problem",
    "3. Evidence",
    "4. Target user and JTBD",
    "5. Proposed solution",
    "6. MVP scope",
    "7. Architecture plan",
    "8. Risks and known failures",
    "9. Business model",
    "10. Metadata and traceability",
]


def cluster(**cambios):
    """Una oportunidad tal como la serializa Rust (camelCase + breakdown)."""
    base = {
        "clusterKey": "complaint:invoice|manual",
        "label": ETIQUETA,
        "intentType": "complaint",
        "keywords": ["invoice", "manual"],
        "subreddits": ["SaaS", "accounting"],
        "mentionCount": 4,
        "communityCount": 2,
        "jobStatement": "Cuando los profesionales enfrentan 'invoice', necesitan ejecutar la tarea.",
        "currentSolutions": ["Quickbooks"],
        "riskFlags": ["event_driven_news_spike"],
        "breakdown": {
            "spreadFactor": 0.4, "frequencyFactor": 0.4, "severityFactor": 0.0,
            "recencyFactor": 1.0, "paidSignalFactor": 1.0, "rawScore": 55.0,
            "finalScore": 55.0,
        },
        "urgencyTier": "MEDIUM",
        "qualified": False,
        "evidence": [
            {"signal_id": "t3_a", "subreddit": "SaaS", "author": "u/ana",
             "quote": "The invoice export is broken, I would pay for a fix.",
             "url": "https://reddit.com/r/SaaS/comments/a", "score": 55.0,
             "created_utc": 1758000000.0},
            {"signal_id": "t3_b", "subreddit": "accounting", "author": "u/bob",
             "quote": "Manual invoice work every week.", "url": "", "score": 50.0},
        ],
        "runId": "11111111-2222-3333-4444-555555555555",
        "dataSource": "reddit",
        "clusterStats": {
            "mentions": 4, "distinct_texts": 4, "severity_undetermined": 4,
            "keywords": [{"keyword": "invoice", "count": 4}, {"keyword": "manual", "count": 3}],
            "pairs": [{"a": "invoice", "b": "manual", "count": 3}],
        },
    }
    base.update(cambios)
    return base


def paginas(pdf: bytes) -> list[str]:
    return [p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages]


class TestDocumentoPdf(unittest.TestCase):

    def test_es_un_pdf_valido_con_portada_indice_y_cuerpo(self):
        pdf = build_pdf(cluster(), "es", version="0.1.0")
        self.assertTrue(pdf.startswith(b"%PDF"))
        texto = paginas(pdf)
        self.assertGreaterEqual(len(texto), 3)
        self.assertIn("Índice", texto[1])

    def test_las_diez_secciones_en_orden_y_en_el_indice(self):
        texto = paginas(build_pdf(cluster(), "es", version="0.1.0"))
        indice = texto[1]
        for titulo in SECCIONES_ES:
            self.assertIn(titulo, indice)
        cuerpo = "\n".join(texto[2:])
        posiciones = [cuerpo.find(t) for t in SECCIONES_ES]
        self.assertNotIn(-1, posiciones, posiciones)
        self.assertEqual(posiciones, sorted(posiciones))

    def test_el_indice_lleva_numeros_de_pagina_reales(self):
        texto = paginas(build_pdf(cluster(), "es", version="0.1.0"))
        # pypdf extrae el número de página justo antes del título, aunque en
        # la página se vean en la misma línea.
        for titulo in SECCIONES_ES:
            encontrado = re.search(r"(\d+)\s*\n\s*" + re.escape(titulo), texto[1])
            self.assertIsNotNone(encontrado, titulo)
            pagina = int(encontrado.group(1))
            self.assertIn(titulo, texto[pagina - 1], titulo)

    def test_el_indice_no_se_lista_a_si_mismo(self):
        indice = paginas(build_pdf(cluster(), "es", version="0.1.0"))[1]
        self.assertEqual(indice.count("Índice"), 1)

    def test_el_espanol_se_extrae_sin_caracteres_rotos(self):
        texto = "\n".join(paginas(build_pdf(cluster(), "es", version="0.1.0")))
        self.assertIn(ETIQUETA, texto)
        self.assertIn("Solución propuesta", texto)

    def test_encabezado_y_pie_en_todas_las_paginas(self):
        texto = paginas(build_pdf(cluster(), "es", version="0.1.0"))
        total = len(texto)
        for numero, pagina in enumerate(texto, start=1):
            self.assertIn(f"página {numero} de {total}", pagina)
            self.assertIn("SENTRA", pagina)

    def test_portada_con_los_datos_de_la_ejecucion(self):
        portada = paginas(build_pdf(cluster(), "es", version="0.1.0"))[0]
        for dato in (ETIQUETA, "55", "11111111-2222-3333-4444-555555555555", "0.1.0", "Reddit"):
            self.assertIn(dato, portada)
        self.assertRegex(portada, r"\d{4}-\d{2}-\d{2}")

    def test_marca_de_agua_en_todas_las_paginas_con_datos_de_demo(self):
        for pagina in paginas(build_pdf(cluster(dataSource="demo"), "es", version="0.1.0")):
            self.assertIn("DATOS DE DEMOSTRACIÓN — NO REALES", pagina)

    def test_sin_marca_de_agua_con_datos_reales(self):
        for pagina in paginas(build_pdf(cluster(dataSource="reddit"), "es", version="0.1.0")):
            self.assertNotIn("DEMOSTRACIÓN", pagina)

    def test_la_evidencia_lleva_comunidad_fecha_y_enlace(self):
        texto = "\n".join(paginas(build_pdf(cluster(), "es", version="0.1.0")))
        self.assertIn("r/SaaS", texto)
        self.assertIn("2025-09-16", texto)
        self.assertIn("https://reddit.com/r/SaaS/comments/a", texto)
        self.assertIn("fecha no registrada", texto)

    def test_plan_de_arquitectura_incluido_o_declarado_no_generado(self):
        con = "\n".join(paginas(build_pdf(
            cluster(), "es", architecture="# FASE 1\n\n## Lógica central\n\n- Paso uno",
            version="0.1.0",
        )))
        self.assertIn("Lógica central", con)
        sin = "\n".join(paginas(build_pdf(cluster(), "es", version="0.1.0")))
        self.assertIn("No generado", sin)

    def test_en_ingles_todo_en_ingles(self):
        texto = paginas(build_pdf(cluster(), "en", version="0.1.0"))
        todo = "\n".join(texto)
        for titulo in SECCIONES_EN:
            self.assertIn(titulo, todo)
        self.assertIn(f"page 1 of {len(texto)}", texto[0])
        self.assertNotIn("página", todo)
        # El enunciado JTBD del motor solo existe en español: no se mezcla.
        self.assertNotIn("Cuando los profesionales", todo)


class TestEndpoint(unittest.TestCase):

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.tmpdir = Path(tempfile.mkdtemp(prefix="rir_pdf_"))
        store = LanceDBStore(db_path=str(self.tmpdir / "lance"), embedder=HashEmbedder(dim=32))
        deps = RadarDependencies(fetcher=SyntheticFetcher(), store=store,
                                 search_engine=HybridSearchEngine(store=store))
        self.client = TestClient(create_app(deps=deps, persist_default=False,
                                            env_path=str(self.tmpdir / ".env")))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        logging.disable(logging.NOTSET)

    def test_devuelve_el_pdf_en_bytes(self):
        respuesta = self.client.post("/api/document/pdf", json={
            "cluster": cluster(), "language": "es", "architecture": None,
        })
        self.assertEqual(respuesta.status_code, 200, respuesta.text[:200])
        self.assertEqual(respuesta.headers["content-type"], "application/pdf")
        self.assertTrue(respuesta.content.startswith(b"%PDF"))


class TestEvidenciaFechada(unittest.TestCase):

    def test_la_agregacion_guarda_la_fecha_de_cada_cita(self):
        from core.intelligence import IntelligenceEngine
        from core.orchestration.aggregation import build_clusters, cluster_to_dict

        engine = IntelligenceEngine(use_transformers_if_available=False)
        senal = engine.analyze_signal(
            item_id="t3_x", title="The invoice export is broken", body="manual work",
            author="u", subreddit="SaaS", created_utc=1758000000.0,
        )
        cita = cluster_to_dict(build_clusters([senal])[0])["evidence"][0]
        self.assertEqual(cita["created_utc"], 1758000000.0)


if __name__ == "__main__":
    unittest.main()
