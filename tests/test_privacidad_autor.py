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
        # texto inventado del doble contiene «hackernews:1»: no cuenta).
        self.assertNotRegex(texto, r"\[[^\]]*hackernews:1|hackernews:1 ·")
        self.assertIn("Se pierde tiempo [E1, E2]", texto)

    def test_el_plan_tambien_cita_con_alias(self):
        from datetime import UTC, datetime

        from core.documents.compose import compose_plan

        doc = compose_plan(detalle(), plan_llm(), "es", model="m", generated_at=datetime(2026, 9, 25, tzinfo=UTC))
        self.assertNotRegex(sin_urls(textos_de(doc)), r"\[[^\]]*hackernews:1|hackernews:1 ·")


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
