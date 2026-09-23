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
from core.intelligence.blueprint import build_blueprint
from core.intelligence.translator import translate
from core.orchestration import RadarDependencies
from core.orchestration.aggregation import build_clusters, cluster_to_dict
from core.orchestration.sidecar_server import _hit_to_camel, create_app
from core.orchestration.source_status import SourceTracker
from core.orchestration.top_n import run_outcome
from core.storage import HashEmbedder, HybridSearchEngine, LanceDBStore

RAIZ = Path(__file__).resolve().parents[1]
TIPOS = json.loads((RAIZ / "ui" / "src-tauri" / "contract" / "ts_types.json").read_text("utf-8"))
SIDECAR = RAIZ / "core" / "orchestration" / "sidecar_server.py"

#: Discrepancias conocidas y ya registradas como hallazgo. Debe quedar vacío
#: cuando se corrigen: el test falla si aparece otra, o si una desaparece
#: sin quitarla de aquí.
EVENTOS_PENDIENTES = {"run:cancelled"}  # AUD-010


def interfaz(nombre: str) -> set[str]:
    return set(TIPOS["interfaces"][nombre])


def snake(nombre: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"_\1", nombre).lower()


def eventos_emitidos() -> dict[str, list[set[str]]]:
    """Cada `type` que emite el sidecar con las claves de cada emisión.

    Se leen del código (literales de dict con clave "type"), no de un
    listado escrito a mano que pueda desfasarse.
    """
    arbol = ast.parse(SIDECAR.read_text(encoding="utf-8"))
    emitidos: dict[str, list[set[str]]] = {}
    for nodo in ast.walk(arbol):
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
                and rama.value.startswith("run:")
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


class TestRespuestasDelSidecar(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rir_contrato_"))
        store = LanceDBStore(db_path=str(self.tmp / "lance"), embedder=HashEmbedder(dim=32))
        self.deps = RadarDependencies(fetcher=SyntheticFetcher(), store=store,
                                      search_engine=HybridSearchEngine(store=store))
        self.client = TestClient(create_app(deps=self.deps, persist_default=False,
                                            env_path=str(self.tmp / ".env")))
        self.cabecera: dict[str, str] = {}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

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

    def test_el_resultado_top_n_entrega_run_top_outcome(self):
        self.assertEqual(set(run_outcome([], 0, "exhausted")), interfaz("RunTopOutcome"))

    def test_la_traduccion_entrega_quote_translation(self):
        self.assertEqual(set(translate(["hola"], "es")[0].to_dict()), interfaz("QuoteTranslation"))

    def test_el_prd_entrega_blueprint_doc(self):
        doc = build_blueprint({"label": "x", "mention_count": 1}, "es").to_dict()
        self.assertEqual(set(doc), interfaz("BlueprintDoc"))
        self.assertEqual(set(doc["mvp"][0]), interfaz("BlueprintPhase"))


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
