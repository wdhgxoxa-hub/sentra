"""
Ningún identificador de autor llega a lo que se ve (R9, Fase 3)
===============================================================

Escaneo 2 de la Fase 3 (25-09): el nombre de un grupo descartado mostraba
«bluesky:did:plc:…#bluesky:did:plc:…». Causa raíz: el id de una pieza de
Bluesky lleva el DID de su autor (`did/rkey`), y ese id se enseñaba en tres
sitios: el nombre de reserva del grupo (su clave interna), los argumentos del
abogado del diablo en «Ver detalle» y las citas del dossier y del plan.

Regla: los ids internos nunca se enseñan (las citas usan alias E1, E2…), y
los textos que se enseñan ocultan DID, at:// y @usuario («[cuenta]», «[usuario]»). La dirección del
original (R5) queda aparte: la de Bluesky lleva el DID y es decisión de Walter.
"""

import re
import unittest
from pathlib import Path
from typing import Any

from core.privacidad import IDENTIFICADOR_DE_AUTOR, ocultar_identificadores
from tests.test_documents_compose import (
    detalle,
    dossier_llm,
    pieza,
    plan_llm,
    textos_de,
)
from tests.test_sidecar_config import ConfigTestCase

UI = Path(__file__).resolve().parents[1] / "ui" / "src"
BSKY = "bluesky:did:plc:fxxq6d7qa7vggtoc7gsn6m2w/3m7kfxojvf22k"
URL = re.compile(r"https?://\S+")


def sin_urls(texto: str) -> str:
    return URL.sub("", texto)


class TestOcultar(unittest.TestCase):
    def test_oculta_did_at_y_arroba(self):
        for texto in ("gracias @martinhowitt por esto", "did:plc:fxxq6d7qa7vggtoc7gsn6m2w dijo",
                      "at://did:plc:abc123/app.bsky.feed.post/xyz", "@ana.bsky.social tiene razón"):
            with self.subTest(texto=texto):
                limpio = ocultar_identificadores(texto)
                self.assertIsNone(IDENTIFICADOR_DE_AUTOR.search(limpio), limpio)
        self.assertEqual(ocultar_identificadores("gracias @martinhowitt por esto"), "gracias [usuario] por esto")

    def test_deja_el_texto_normal_y_los_correos(self):
        for texto in ("Pierdo horas persiguiendo documentos", "escribe a ana@ejemplo.com", "C# y F#"):
            self.assertEqual(ocultar_identificadores(texto), texto)


class TestDocumentos(unittest.TestCase):
    def test_el_dossier_cita_con_alias_y_no_enseña_ids_de_bluesky(self):
        from datetime import UTC, datetime

        from core.documents.compose import compose_dossier
        from tests.test_documents_compose import cita

        bluesky = {**pieza(BSKY, "bluesky"), "text": "Queja de @martinhowitt: perseguir documentos"}
        det = detalle(evidence=[pieza("hackernews:1"), bluesky],
                      gates=[{"gate": "G1", "passed": False, "value": 1, "threshold": 2, "evidence_ids": [BSKY]}],
                      advocate={"verdict_before": "CONSTRUIR", "verdict_after": "CONSTRUIR", "downgraded": False,
                                "reason": None, "discarded": [],
                                "arguments": [{"claim": "pocos", "evidence_ids": [BSKY], "severity": "menor"}]})
        doc = compose_dossier(det, dossier_llm(problem=[cita("hackernews:1", BSKY, texto="Se pierde tiempo")]),
                              "es", model="m", generated_at=datetime(2026, 9, 25, tzinfo=UTC))
        texto = sin_urls(textos_de(doc))
        self.assertIsNone(IDENTIFICADOR_DE_AUTOR.search(texto), IDENTIFICADOR_DE_AUTOR.search(texto))
        # Ningún id interno en citas ni firmas, tampoco los que no llevan autor (el
        # texto inventado del doble contiene «hackernews:1», y su dirección también:
        # un enlace Markdown [dirección](destino) no es una cita).
        self.assertNotRegex(texto, r"\[[^\]]*hackernews:1[^\]]*\](?!\()|hackernews:1 ·")
        self.assertIn("Se pierde tiempo [E1, E2]", texto)

    def test_el_plan_tambien_cita_con_alias(self):
        from datetime import UTC, datetime

        from core.documents.compose import compose_plan

        doc = compose_plan(detalle(), plan_llm(), "es", model="m", generated_at=datetime(2026, 9, 25, tzinfo=UTC))
        self.assertNotRegex(sin_urls(textos_de(doc)), r"\[[^\]]*hackernews:1[^\]]*\](?!\()|hackernews:1 ·")


BSKY_URL = "https://bsky.app/profile/did:plc:fxxq6d7qa7vggtoc7gsn6m2w/post/3m7kfxojvf22k"
#: Así se guardó la firma antes de D-M12 (el dossier guardado tiene 22 así): los
#: datos no se reescriben, cada salida la convierte al pintarla.
FIRMA_GUARDADA = f"E1 · 2026-09-20 · Bluesky · bsky.app · {BSKY_URL}"


def documento_con_firma(firma: str = FIRMA_GUARDADA) -> Any:
    from core.documents.model import Block, DocumentModel, Section

    return DocumentModel(language="es", kind="dossier", title="Dossier", data_source="real",
                         cover=(("Veredicto", "CONSTRUIR"),),
                         sections=(Section("evidencia", "10. Evidencia citada",
                                           (Block("quote", "Persigo documentos cada mes", signature=firma),)),))


class TestDireccionEnDocumentos(unittest.TestCase):
    """D-M12 (Walter): la dirección se guarda completa, con el DID (R5), pero el DID
    nunca se ve como texto (R9): va solo en el destino de un enlace."""

    def test_direccion_visible_como_en_la_interfaz(self):
        from core.privacidad import direccion_visible

        self.assertEqual(direccion_visible(BSKY_URL), "bsky.app/profile/…/post/3m7kfxojvf22k")
        self.assertEqual(direccion_visible("https://bsky.app/profile/ana.bsky.social/post/3m"),
                         "bsky.app/profile/…/post/3m")
        self.assertEqual(direccion_visible("https://ejemplo.org/@ana/123"), "ejemplo.org/…/123")
        self.assertEqual(direccion_visible("https://ejemplo.org/bluesky:did:plc:abc/3m"), "ejemplo.org/…/3m")
        self.assertEqual(direccion_visible("https://stackoverflow.com/q/2"), "stackoverflow.com/q/2")

    def test_markdown_el_did_solo_en_el_destino_del_enlace(self):
        md = documento_con_firma().to_markdown()
        self.assertIn(f"[bsky.app/profile/…/post/3m7kfxojvf22k]({BSKY_URL})", md)
        fuera_de_destinos = re.sub(r"\]\([^)]*\)", "]", md)
        self.assertIsNone(IDENTIFICADOR_DE_AUTOR.search(fuera_de_destinos), fuera_de_destinos)

    def test_pdf_el_did_solo_en_el_destino_del_enlace(self):
        import io

        from pypdf import PdfReader

        from core.documents.pdf_report import render_pdf

        lector = PdfReader(io.BytesIO(render_pdf(documento_con_firma())))
        texto = " ".join(p.extract_text() or "" for p in lector.pages)
        self.assertIsNone(IDENTIFICADOR_DE_AUTOR.search(texto), texto)
        self.assertIn("bsky.app/profile/…/post/3m7kfxojvf22k", texto.replace("\n", ""))
        destinos = [a.get_object()["/A"]["/URI"] for p in lector.pages for a in (p.get("/Annots") or [])
                    if "/A" in a.get_object()]
        self.assertIn(BSKY_URL, destinos)


def documento_guardado_antes_de_los_alias() -> Any:
    """Como el dossier guardado de verdad (antes de af3644c): ids crudos de Bluesky en
    las citas y al principio de la firma. D-M12: no se reescribe; se oculta al pintar."""
    from core.documents.model import Block, DocumentModel, Section

    cita_cruda = "bluesky:did:plc:2v2d5k3ca4hqat2e5k3pnvvt/3ms73bidujc2n"
    return DocumentModel(language="es", kind="dossier", title="Dossier", data_source="real",
                         cover=(("Veredicto", "CONSTRUIR"),), sections=(
        Section("problema", "2. El problema", (
            Block("bullets", items=(f"Genera frustración. [{cita_cruda}, github:5282404259]",)),
            Block("code", "npm i @tanstack/react-query"),
        )),
        Section("evidencia", "10. Evidencia citada", (
            Block("quote", "Persigo documentos", signature=f"{cita_cruda} · 2026-09-20 · Bluesky · bsky.app · {BSKY_URL}"),
        )),
    ))


class TestDocumentosGuardadosAntes(unittest.TestCase):
    """Walter: los datos guardados no se reescriben; lo que importa es que nada se vea."""

    def test_markdown_sin_did_fuera_de_los_destinos(self):
        md = documento_guardado_antes_de_los_alias().to_markdown()
        fuera = re.sub(r"\]\([^)]*\)", "]", md)
        self.assertNotIn("did:", fuera, fuera)
        self.assertIn(f"]({BSKY_URL})", md)
        self.assertIn("npm i @tanstack/react-query", md, "un paquete de npm no es una cuenta")

    def test_pdf_sin_did_en_el_texto(self):
        import io

        from pypdf import PdfReader

        from core.documents.pdf_report import render_pdf

        lector = PdfReader(io.BytesIO(render_pdf(documento_guardado_antes_de_los_alias())))
        texto = " ".join(p.extract_text() or "" for p in lector.pages)
        self.assertNotIn("did:", texto, texto)
        self.assertIn("@tanstack/react-query", texto)


class TestInterfaz(unittest.TestCase):
    def test_la_interfaz_no_pinta_claves_ni_ids_de_piezas(self):
        """Ni la clave interna del grupo como nombre, ni los ids de las piezas."""
        for archivo in UI.rglob("*.ts*"):
            if archivo.name.endswith(".test.ts"):
                continue
            with self.subTest(archivo=archivo.name):
                fuente = archivo.read_text("utf-8")
                self.assertNotRegex(fuente, r"\|\|\s*v\.clusterKey")
                self.assertNotRegex(fuente, r"evidenceIds\.join")



class TestTopDelJuez(ConfigTestCase):
    def test_no_envia_la_clave_interna_y_oculta_identificadores(self):
        from unittest import mock

        from core.orchestration.sidecar import judge
        from tests.test_sidecar_judge import LEIDO

        original: dict[str, Any] = LEIDO["verdicts"][0]  # type: ignore[index]
        veredicto = {**original, "cluster_key": f"{BSKY}#{BSKY}",
                     "evidence": [{**original["evidence"][0], "id": BSKY,
                                   "excerpt": "Gracias @martinhowitt, persigo documentos cada mes"}]}
        with mock.patch.object(judge, "_leer_top", return_value={**LEIDO, "verdicts": [veredicto], "rest": []}):
            cuerpo = self.client.get("/api/judge/top").json()
        self.assertNotIn("clusterKey", cuerpo["verdicts"][0])
        self.assertNotIn("@martinhowitt", cuerpo["verdicts"][0]["evidence"][0]["excerpt"])


if __name__ == "__main__":
    unittest.main()
