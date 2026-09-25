"""
Contratos Python → TypeScript (AUD-029)
=======================================

Lo que el sidecar produce y la interfaz consume se compara con los tipos de
`ui/src/types/radar.ts`, extraídos por el compilador de TypeScript en
`ui/src-tauri/contract/ts_types.json` (`npm run contracts`). Los contratos
Rust → TS viven en `ui/src-tauri/src/commands/contract_returns_tests.rs`.
"""

import ast
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from core.orchestration.sidecar_server import create_app
from tests._sin_red import prohibir_red_real

RAIZ = Path(__file__).resolve().parents[1]
TIPOS = json.loads((RAIZ / "ui" / "src-tauri" / "contract" / "ts_types.json").read_text("utf-8"))
# Los eventos del escaneo multifuente, el núcleo (source:*) y el router (scan:*, error).
MULTIFUENTE = (RAIZ / "core" / "sources" / "scan.py",
               RAIZ / "core" / "orchestration" / "sidecar" / "multiscan.py")

def interfaz(nombre: str) -> set[str]:
    return set(TIPOS["interfaces"][nombre])


def eventos_emitidos(archivos: tuple[Path, ...], es_evento) -> dict[str, list[set[str]]]:
    """Cada `type` que emite el sidecar con las claves de cada emisión.

    Se leen del código (literales de dict con clave "type"), no de un
    listado escrito a mano que pueda desfasarse.
    """
    emitidos: dict[str, list[set[str]]] = {}
    nodos = [n for archivo in archivos
             for n in ast.walk(ast.parse(archivo.read_text(encoding="utf-8")))]
    for nodo in nodos:
        if not isinstance(nodo, ast.Dict):
            continue
        claves = [
            k.value for k in nodo.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        ]
        if "type" not in claves:
            continue
        valor = nodo.values[claves.index("type")]
        ramas = [valor.body, valor.orelse] if isinstance(valor, ast.IfExp) else [valor]
        for rama in ramas:
            if (
                isinstance(rama, ast.Constant)
                and isinstance(rama.value, str)
                and es_evento(rama.value)
            ):
                emitidos.setdefault(rama.value, []).append(set(claves))
    return emitidos


class TestFixtureAlDia(unittest.TestCase):

    @unittest.skipUnless(shutil.which("node"), "node no disponible")
    def test_el_fixture_refleja_los_tipos_ts_actuales(self):
        resultado = subprocess.run(
            ["node", "scripts/generate-contract-fixtures.mjs", "--check"],
            cwd=RAIZ / "ui", capture_output=True, text=True, check=False,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)


class TestEventosMultifuente(unittest.TestCase):

    def emitidos(self):
        return eventos_emitidos(
            MULTIFUENTE, lambda t: t.startswith(("source:", "scan:", "judge:")) or t == "error")

    def test_cada_evento_emitido_existe_en_la_union_y_viceversa(self):
        self.assertEqual(set(self.emitidos()), set(TIPOS["uniones"]["MultiScanEvent"]))

    def test_cada_emision_lleva_las_claves_de_su_variante(self):
        union = TIPOS["uniones"]["MultiScanEvent"]
        for tipo, emisiones in self.emitidos().items():
            for claves in emisiones:
                self.assertEqual(claves, set(union[tipo]), tipo)


class TestRespuestasDelSidecar(unittest.TestCase):

    def setUp(self):
        prohibir_red_real(self)
        self.tmp = Path(tempfile.mkdtemp(prefix="rir_contrato_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        token = "c0" * 32  # como el de la aplicación: 64 hex (D-B)
        self.client = TestClient(create_app(token=token, persist_default=False,
                                            env_path=str(self.tmp / ".env")))
        self.cabecera = {"Authorization": f"Bearer {token}"}

    def test_la_busqueda_entrega_evidence_search_hit(self):
        from unittest import mock

        from core.orchestration.sidecar import search
        from tests.test_sidecar_search import HITS

        with mock.patch.object(search, "_disponible", return_value=True), \
                mock.patch.object(search, "_buscar", return_value=HITS):
            cuerpo = self.client.post("/api/search", json={"query": "x"}, headers=self.cabecera).json()
        self.assertEqual(set(cuerpo["hits"][0]), interfaz("EvidenceSearchHit"))
        self.assertEqual(set(cuerpo["hits"][0]["attribution"]), interfaz("EvidenceAttribution"))

    def test_la_configuracion_entrega_app_settings(self):
        cuerpo = self.client.get("/api/config", headers=self.cabecera).json()
        self.assertEqual(set(cuerpo), interfaz("AppSettings"))
        self.assertEqual(set(cuerpo["gemini"]), interfaz("GeminiSummary"))

    def test_las_fuentes_entregan_sources_overview_y_source_card(self):
        cuerpo = self.client.get("/api/sources", headers=self.cabecera).json()
        self.assertEqual(set(cuerpo), interfaz("SourcesOverview"))
        self.assertEqual(set(cuerpo["sources"][0]), interfaz("SourceCard"))

    def test_cada_credencial_entrega_source_credential_state(self):
        from core.orchestration.sidecar.sources import _en_camel
        from core.sources.base import CostModel, CredentialField, SourceAdapter
        from core.sources.registry import source_status

        class ConClave(SourceAdapter):
            id, display_name, terms_url = "x", "X", "https://example.com/t"
            commercial_use_allowed, requires_credentials = True, True
            cost_model = CostModel(unit="request")
            credential_fields = (CredentialField(name="token", env_var="RIR_X_TOKEN"),)

            async def probe(self):
                raise NotImplementedError

            def search(self, query):
                raise NotImplementedError

        estado = _en_camel(source_status(ConClave, {}, None, False).model_dump(mode="json"))
        self.assertEqual(set(estado["credentialFields"][0]), interfaz("SourceCredentialState"))

    def test_probar_entrega_source_probe_result(self):
        # Sin red: el camino de «faltan credenciales» devuelve la misma forma.
        from datetime import UTC, datetime

        from core.orchestration.sidecar.sources import _en_camel
        from core.sources.base import ProbeResult
        from core.sources.errors import SourceCredentialsMissing

        error = SourceCredentialsMissing("x", "faltan: token")
        forma = _en_camel(ProbeResult(ok=False, code=error.code, detail=error.detail,
                                      checked_at=datetime(2026, 9, 1, tzinfo=UTC)).model_dump(mode="json"))
        self.assertEqual(set(forma), interfaz("SourceProbeResult"))

    def test_la_atribucion_entrega_evidence_attribution(self):
        from datetime import UTC, datetime

        from core.evidence.model import EvidenceItem
        from core.sources.attribution import attribution

        ahora = datetime(2026, 9, 1, tzinfo=UTC)
        pieza = EvidenceItem(id="stackexchange:1", source="stackexchange", community="Stack Overflow",
                             kind="question", text="x", url="https://stackoverflow.com/q/1",
                             author_hash=None, created_at=ahora, fetched_at=ahora,
                             data_source="real")
        self.assertEqual(set(attribution(pieza)), interfaz("EvidenceAttribution"))

    def test_el_top_del_juez_entrega_judge_top(self):
        from unittest import mock

        from core.orchestration.sidecar import judge
        from tests.test_sidecar_judge import LEIDO

        with mock.patch.object(judge, "_leer_top", return_value={**LEIDO, "rest": LEIDO["verdicts"]}):
            cuerpo = self.client.get("/api/judge/top", headers=self.cabecera).json()
        self.assertEqual(set(cuerpo), interfaz("JudgeTop"))
        self.assertEqual(set(cuerpo["rest"][0]), interfaz("JudgeVerdict"))
        self.assertEqual(set(cuerpo["currentVersions"]), interfaz("JudgeVersions"))
        self.assertEqual(set(cuerpo["run"]), interfaz("RunOverview"))
        self.assertEqual(set(cuerpo["latestRun"]), interfaz("RunOverview"))
        veredicto = cuerpo["verdicts"][0]
        self.assertEqual(set(veredicto), interfaz("JudgeVerdict"))
        self.assertEqual(set(veredicto["gates"][0]), interfaz("JudgeGate"))
        self.assertEqual(set(veredicto["dimensions"][0]), interfaz("JudgeDimension"))
        self.assertEqual(set(veredicto["advocate"]), interfaz("JudgeAdvocate"))
        self.assertEqual(set(veredicto["advocate"]["arguments"][0]), interfaz("AdvocateArgumentView"))
        self.assertEqual(set(veredicto["evidence"][0]), interfaz("JudgeEvidence"))
        self.assertEqual(set(veredicto["evidence"][0]["attribution"]), interfaz("EvidenceAttribution"))

    def test_el_estado_de_los_documentos_entrega_documents_status(self):
        cuerpo = self.client.get("/api/documents/status", headers=self.cabecera,
                                 params={"verdictId": "11111111-1111-1111-1111-111111111111"}).json()
        self.assertEqual(set(cuerpo), interfaz("DocumentsStatus"))
        self.assertEqual(set(cuerpo["dossier"]), interfaz("SavedByLanguage"))

    def test_el_feed_de_evidencia_entrega_evidence_feed(self):
        from unittest import mock

        from core.orchestration.sidecar import judge
        from tests.test_sidecar_judge import FEED

        with mock.patch.object(judge, "_leer_feed", return_value=FEED):
            cuerpo = self.client.get("/api/evidence/recent", headers=self.cabecera).json()
        self.assertEqual(set(cuerpo), interfaz("EvidenceFeed"))
        self.assertEqual(set(cuerpo["items"][0]), interfaz("EvidenceFeedEntry"))
        self.assertEqual(set(cuerpo["items"][0]["attribution"]), interfaz("EvidenceAttribution"))

if __name__ == "__main__":
    unittest.main()
