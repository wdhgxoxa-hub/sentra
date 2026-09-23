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
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from core.ingestion.synthetic import SyntheticFetcher
from core.intelligence import IntelligenceEngine
from core.intelligence.translator import translate
from core.orchestration import RadarDependencies
from core.orchestration.aggregation import build_clusters, cluster_to_dict
from core.orchestration.sidecar.search import hit_to_camel as _hit_to_camel
from core.orchestration.sidecar_server import create_app
from core.orchestration.source_status import SourceTracker
from core.orchestration.top_n import run_outcome
from core.storage import HashEmbedder, HybridSearchEngine, LanceDBStore
from tests._sin_red import prohibir_red_real

RAIZ = Path(__file__).resolve().parents[1]
TIPOS = json.loads((RAIZ / "ui" / "src-tauri" / "contract" / "ts_types.json").read_text("utf-8"))
# Los eventos SSE los emite el router de escaneo (R-D).
SIDECAR = RAIZ / "core" / "orchestration" / "sidecar" / "scan.py"
# Los del escaneo multifuente, el núcleo (source:*) y el router (scan:*, error).
MULTIFUENTE = (RAIZ / "core" / "sources" / "scan.py",
               RAIZ / "core" / "orchestration" / "sidecar" / "multiscan.py")

#: Discrepancias conocidas y ya registradas como hallazgo. Debe quedar vacío
#: cuando se corrigen: el test falla si aparece otra, o si una desaparece
#: sin quitarla de aquí.
EVENTOS_PENDIENTES: set[str] = set()


def interfaz(nombre: str) -> set[str]:
    return set(TIPOS["interfaces"][nombre])


def snake(nombre: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"_\1", nombre).lower()


def eventos_emitidos(
    archivos: tuple[Path, ...] = (SIDECAR,), es_evento=lambda t: t.startswith("run:"),
) -> dict[str, list[set[str]]]:
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


class TestEventos(unittest.TestCase):

    def test_cada_evento_emitido_existe_en_la_union_y_viceversa(self):
        union = set(TIPOS["uniones"]["RadarEvent"])
        emitidos = set(eventos_emitidos())
        self.assertEqual(emitidos - union, EVENTOS_PENDIENTES,
                         "eventos que emite el sidecar y la interfaz no tipa")
        self.assertEqual(union - emitidos, set(), "variantes TS que nadie emite")

    def test_cada_emision_lleva_las_claves_de_su_variante(self):
        union = TIPOS["uniones"]["RadarEvent"]
        for tipo, emisiones in eventos_emitidos().items():
            if tipo in EVENTOS_PENDIENTES:
                continue
            for claves in emisiones:
                self.assertEqual(claves, set(union[tipo]), tipo)


class TestEventosMultifuente(unittest.TestCase):

    def emitidos(self):
        return eventos_emitidos(
            MULTIFUENTE, lambda t: t.startswith(("source:", "scan:")) or t == "error")

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
        store = LanceDBStore(db_path=str(self.tmp / "lance"), embedder=HashEmbedder(dim=32))
        self.deps = RadarDependencies(fetcher=SyntheticFetcher(), store=store,
                                      search_engine=HybridSearchEngine(store=store))
        token = "c0" * 32  # como el de la aplicación: 64 hex (D-B)
        self.client = TestClient(create_app(deps=self.deps, token=token, persist_default=False,
                                            env_path=str(self.tmp / ".env")))
        self.cabecera = {"Authorization": f"Bearer {token}"}


    def test_la_busqueda_entrega_hybrid_search_hit(self):
        class Hit:
            id = text = subreddit = author = urgency_tier = job_statement = "x"
            current_solution = None
            opportunity_score = rrf_score = 1.0
            dense_rank = bm25_rank = bm25_score = data_source = None

        self.assertEqual(set(_hit_to_camel(Hit())), interfaz("HybridSearchHit"))

    def test_la_configuracion_entrega_app_settings(self):
        cuerpo = self.client.get("/api/config", headers=self.cabecera).json()
        self.assertEqual(set(cuerpo), interfaz("AppSettings"))
        self.assertEqual(set(cuerpo["credentials"]), interfaz("CredentialsSummary"))
        self.assertEqual(set(cuerpo["gemini"]), interfaz("GeminiSummary"))

    def test_el_estado_de_la_fuente_entrega_source_status(self):
        self.assertEqual(set(SourceTracker().snapshot("demo", False)), interfaz("SourceStatus"))

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

        estado = _en_camel(source_status(ConClave, {}, None, False).model_dump(mode="json"))
        self.assertEqual(set(estado["credentialFields"][0]), interfaz("SourceCredentialState"))

    def test_probar_entrega_source_probe_result(self):
        # Sin red: el camino de «faltan credenciales» devuelve la misma forma.
        from core.orchestration.sidecar.sources import _en_camel
        from core.sources.base import ProbeResult
        from core.sources.errors import SourceCredentialsMissing

        error = SourceCredentialsMissing("x", "faltan: token")
        forma = _en_camel(ProbeResult(ok=False, code=error.code, detail=error.detail,
                                      checked_at="2026-09-01T00:00:00Z").model_dump(mode="json"))
        self.assertEqual(set(forma), interfaz("SourceProbeResult"))

    def test_el_resultado_top_n_entrega_run_top_outcome(self):
        self.assertEqual(set(run_outcome([], 0, "exhausted")), interfaz("RunTopOutcome"))

    def test_la_traduccion_entrega_quote_translation(self):
        self.assertEqual(set(translate(["hola"], "es")[0].to_dict()), interfaz("QuoteTranslation"))

    def test_el_prd_entrega_blueprint_doc(self):
        # Lo que viaja es la respuesta del endpoint: PRD + secciones del
        # DocumentModel (D-H).
        doc = self.client.post("/api/blueprint", headers=self.cabecera, json={
            "cluster": {"label": "x", "mention_count": 1}, "language": "es"}).json()
        self.assertEqual(set(doc), interfaz("BlueprintDoc"))
        self.assertEqual(set(doc["mvp"][0]), interfaz("BlueprintPhase"))
        self.assertEqual(set(doc["sections"][0]), interfaz("DocumentSection"))
        self.assertEqual(set(doc["sections"][0]["blocks"][0]), interfaz("DocumentBlock"))


class TestLoQueViajaPorPostgres(unittest.TestCase):
    """Estas estructuras las escribe Python en jsonb y Rust las reenvía."""

    @classmethod
    def setUpClass(cls):
        motor = IntelligenceEngine(use_transformers_if_available=False)
        senal = motor.analyze_signal(item_id="t3_x", title="The invoice export is broken",
                                     body="manual work", author="u", subreddit="SaaS",
                                     created_utc=1758000000.0)
        cls.cluster = cluster_to_dict(build_clusters([senal])[0])

    def test_la_evidencia_coincide_con_evidence_quote_en_snake_case(self):
        # Rust la lee en snake_case y la entrega en camelCase (radar.rs).
        esperado = {snake(k) for k in interfaz("EvidenceQuote")}
        self.assertEqual(set(self.cluster["evidence"][0]), esperado)

    def test_las_cifras_coinciden_con_cluster_stats(self):
        self.assertEqual(set(self.cluster["stats"]), interfaz("ClusterStats"))


if __name__ == "__main__":
    unittest.main()
