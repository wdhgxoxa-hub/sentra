"""
Suite de pruebas de la Fase 5: core/orchestration
=================================================
Cubre el puente entre capas (AnalyzedSignal -> OpportunityRecord), los cinco
nodos del grafo, el ciclo controlado, la resiliencia ante fallos de nodo, el
runner de alto nivel y las tres herramientas MCP.

Ningun test toca la red: el fetcher siempre se inyecta.
"""

import asyncio
import logging
import shutil
import tempfile
import unittest

from core.orchestration import (
    MIN_OPPORTUNITY_SCORE,
    RadarDependencies,
    RadarPipeline,
    RadarState,
    build_graph,
    new_state,
    signal_to_record,
)
from core.orchestration.graph import (
    fetch_node,
    filter_node,
    intelligence_node,
    quality_gate_node,
    storage_node,
)
from core.storage import HashEmbedder, HybridSearchEngine, LanceDBStore

def setUpModule():
    """
    Silencia el logging durante la suite.

    Varios tests provocan fallos a propósito (un fetcher que revienta, un
    almacén que no escribe) y se comprueban por el estado devuelto, no por la
    salida. Sin esto, los errores esperados ensucian el informe y esconden los
    inesperados.
    """
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


TEST_DIM = 64

# Corte alcanzable por una señal individual.
#
# El scoring de la Fase 3 está calibrado para oportunidades AGREGADAS: los
# factores `spread` y `frequency` miden en cuántas comunidades y cuántas veces
# se repite un problema. Una señal suelta los tiene clavados en el mínimo, de
# modo que su techo real ronda los 25 puntos y jamás alcanza el corte por
# defecto de 60. Los tests que ejercitan la MECÁNICA del gate usan este corte
# alcanzable; el techo real queda caracterizado en su propio test.
REACHABLE_CUT = 20.0

# Un post con dolor claro y reciente, pensado para superar el corte.
PAIN_POST = {
    "id": "t3_pain",
    "subreddit": "smallbusiness",
    "title": "I waste hours every week on manual invoice exports",
    "selftext": (
        "There is no way to export invoices to CSV. I am struggling with this "
        "every single week and it is a huge pain. I would gladly pay for a tool "
        "that fixes this problem."
    ),
    "author": "u/frustrated",
    "score": 120,
    "created_utc": 4102444800.0,  # 2100: fuerza recencia maxima y score alto
    "url": "https://reddit.com/r/smallbusiness/pain",
}

# Un post con patron de afiliado: debe ser vetado por el gate.
SPAM_POST = {
    "id": "t3_spam",
    "subreddit": "smallbusiness",
    "title": "This tool fixed my broken invoice problem",
    "selftext": (
        "I was struggling with invoices. Use my referral link and promo code "
        "SAVE20 for a discount, ref=12345 utm_source=reddit."
    ),
    "author": "u/promoter",
    "score": 5,
    "created_utc": 4102444800.0,
    "url": "https://reddit.com/r/smallbusiness/spam",
}

# Un post sin ninguna senal de dolor: lo descarta el filtro.
NOISE_POST = {
    "id": "t3_noise",
    "subreddit": "smallbusiness",
    "title": "Just saying hello to everyone here",
    "selftext": "Happy friday, hope you all have a great weekend.",
    "author": "u/chatty",
    "score": 3,
    "created_utc": 4102444800.0,
    "url": "https://reddit.com/r/smallbusiness/noise",
}


class FakeFetcher:
    """Fetcher inyectable que sirve paginas predefinidas y cuenta llamadas."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def __call__(self, subreddit, limit, sort, cursor=None):
        self.calls.append({"subreddit": subreddit, "limit": limit,
                           "sort": sort, "cursor": cursor})
        index = 0 if cursor is None else int(cursor)
        if index >= len(self.pages):
            return [], None
        next_cursor = str(index + 1) if index + 1 < len(self.pages) else None
        return list(self.pages[index]), next_cursor


class OrchestrationTestCase(unittest.TestCase):
    """Base con almacen temporal y dependencias reales salvo la red."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="rir_orch_")
        self.store = LanceDBStore(
            db_path=self.tmpdir, embedder=HashEmbedder(dim=TEST_DIM)
        )
        self.fetcher = FakeFetcher([[PAIN_POST, SPAM_POST, NOISE_POST]])
        self.deps = RadarDependencies(
            fetcher=self.fetcher,
            store=self.store,
            search_engine=HybridSearchEngine(store=self.store),
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def run_all_nodes(self, state, min_score=MIN_OPPORTUNITY_SCORE):
        """Recorre los cinco nodos en orden, fusionando el estado."""
        for node in (fetch_node, filter_node, intelligence_node, storage_node):
            state = {**state, **node(state, self.deps)}
        return {**state, **quality_gate_node(state, self.deps, min_score)}


class TestState(unittest.TestCase):

    def test_new_state_carries_the_request_parameters(self):
        state = new_state(subreddit="devops", limit=25, sort="new")
        self.assertEqual(state["subreddit"], "devops")
        self.assertEqual(state["limit"], 25)
        self.assertEqual(state["sort"], "new")

    def test_new_state_starts_with_empty_collections(self):
        state = new_state(subreddit="devops")
        for key in ("raw_items", "filtered_items", "signals",
                    "stored_ids", "qualified", "errors"):
            self.assertEqual(state[key], [], f"{key} deberia arrancar vacio")

    def test_new_state_starts_at_cycle_zero(self):
        self.assertEqual(new_state(subreddit="devops")["cycle"], 0)

    def test_radar_state_declares_the_canonical_keys(self):
        for key in ("subreddit", "limit", "sort", "cursor", "cycle",
                    "raw_items", "filtered_items", "signals", "stored_ids",
                    "qualified", "stats", "errors"):
            self.assertIn(key, RadarState.__annotations__)


class TestSignalToRecord(unittest.TestCase):
    """El puente entre el modelo analitico y el de persistencia."""

    @classmethod
    def setUpClass(cls):
        from core.intelligence import IntelligenceEngine

        cls.engine = IntelligenceEngine(use_transformers_if_available=False)
        cls.signal = cls.engine.analyze_signal(
            item_id=PAIN_POST["id"],
            title=PAIN_POST["title"],
            body=PAIN_POST["selftext"],
            author=PAIN_POST["author"],
            subreddit=PAIN_POST["subreddit"],
            created_utc=PAIN_POST["created_utc"],
            url=PAIN_POST["url"],
        )

    def test_identity_fields_are_carried_over(self):
        record = signal_to_record(self.signal)
        self.assertEqual(record.id, PAIN_POST["id"])
        self.assertEqual(record.subreddit, PAIN_POST["subreddit"])
        self.assertEqual(record.author, PAIN_POST["author"])

    def test_opportunity_score_comes_from_the_score_breakdown(self):
        record = signal_to_record(self.signal)
        self.assertEqual(
            record.opportunity_score, self.signal.score_breakdown.final_score
        )

    def test_urgency_tier_comes_from_the_score_breakdown(self):
        self.assertEqual(
            signal_to_record(self.signal).urgency_tier,
            self.signal.score_breakdown.urgency_tier,
        )

    def test_jtbd_synthesis_is_carried_over(self):
        record = signal_to_record(self.signal)
        self.assertEqual(record.job_statement, self.signal.jtbd.job_statement)
        self.assertEqual(
            record.workaround_detected, self.signal.jtbd.workaround_detected
        )

    def test_classification_labels_are_carried_over(self):
        record = signal_to_record(self.signal)
        self.assertEqual(record.buying_intent, self.signal.buying_intent)
        self.assertEqual(record.pain_severity, self.signal.pain_severity)

    def test_reddit_upvotes_are_taken_from_the_raw_item(self):
        record = signal_to_record(self.signal, raw_score=PAIN_POST["score"])
        self.assertEqual(record.score, PAIN_POST["score"])

    def test_record_has_no_vector_so_the_store_generates_it(self):
        self.assertEqual(signal_to_record(self.signal).vector, [])


class TestFetchNode(OrchestrationTestCase):

    def test_fetch_populates_raw_items(self):
        result = fetch_node(new_state(subreddit="smallbusiness"), self.deps)
        self.assertEqual(len(result["raw_items"]), 3)

    def test_fetch_forwards_the_request_parameters(self):
        fetch_node(
            new_state(subreddit="devops", limit=7, sort="new"), self.deps
        )
        self.assertEqual(self.fetcher.calls[0]["subreddit"], "devops")
        self.assertEqual(self.fetcher.calls[0]["limit"], 7)
        self.assertEqual(self.fetcher.calls[0]["sort"], "new")

    def test_fetch_records_the_next_cursor(self):
        deps = RadarDependencies(
            fetcher=FakeFetcher([[PAIN_POST], [NOISE_POST]]), store=self.store
        )
        self.assertEqual(
            fetch_node(new_state(subreddit="x"), deps)["cursor"], "1"
        )

    def test_exhausted_fetcher_yields_no_cursor(self):
        self.assertIsNone(
            fetch_node(new_state(subreddit="x"), self.deps)["cursor"]
        )

    def test_a_failing_fetcher_is_recorded_instead_of_raising(self):
        def broken(*args, **kwargs):
            raise ConnectionError("reddit no responde")

        result = fetch_node(
            new_state(subreddit="x"), RadarDependencies(fetcher=broken, store=self.store)
        )
        self.assertEqual(result["raw_items"], [])
        self.assertTrue(any("reddit no responde" in e for e in result["errors"]))


class TestFilterNode(OrchestrationTestCase):

    def _filtered_ids(self):
        state = new_state(subreddit="smallbusiness")
        state = {**state, **fetch_node(state, self.deps)}
        result = filter_node(state, self.deps)
        return {item["id"] for item in result["filtered_items"]}, result

    def test_pain_post_survives_the_filter(self):
        ids, _ = self._filtered_ids()
        self.assertIn("t3_pain", ids)

    def test_post_without_pain_keywords_is_discarded(self):
        ids, _ = self._filtered_ids()
        self.assertNotIn("t3_noise", ids)

    def test_affiliate_post_is_discarded(self):
        ids, _ = self._filtered_ids()
        self.assertNotIn("t3_spam", ids)

    def test_filter_reports_how_many_it_dropped(self):
        _, result = self._filtered_ids()
        self.assertEqual(result["stats"]["filtered_out"], 2)


class TestIntelligenceNode(OrchestrationTestCase):

    def setUp(self):
        super().setUp()
        self.state = new_state(subreddit="smallbusiness")
        self.state = {**self.state, **fetch_node(self.state, self.deps)}
        self.state = {**self.state, **filter_node(self.state, self.deps)}

    def test_every_filtered_item_becomes_a_signal(self):
        result = intelligence_node(self.state, self.deps)
        self.assertEqual(
            len(result["signals"]), len(self.state["filtered_items"])
        )

    def test_signals_carry_a_computed_opportunity_score(self):
        signal = intelligence_node(self.state, self.deps)["signals"][0]
        self.assertGreater(signal.score_breakdown.final_score, 0.0)

    def test_signals_carry_a_jtbd_statement(self):
        signal = intelligence_node(self.state, self.deps)["signals"][0]
        self.assertTrue(signal.jtbd.job_statement)

    def test_a_signal_is_scored_as_a_single_voice(self):
        """
        El `spread` de una señal individual no debe heredar el contexto del
        lote: venir acompañada de otras quejas no la hace más difundida. La
        difusión real la mide la agregación.
        """
        signal = intelligence_node(self.state, self.deps)["signals"][0]
        self.assertEqual(signal.temporal_metrics.community_count, 1)
        self.assertAlmostEqual(signal.score_breakdown.spread_factor, 0.2)


class TestStorageNode(OrchestrationTestCase):

    def setUp(self):
        super().setUp()
        self.state = new_state(subreddit="smallbusiness")
        self.state = self.run_all_nodes(self.state)

    def test_signals_are_persisted(self):
        self.assertGreater(self.store.count_records(), 0)

    def test_stored_ids_are_reported(self):
        self.assertIn("t3_pain", self.state["stored_ids"])

    def test_persisted_record_is_retrievable_with_its_synthesis(self):
        stored = self.store.get_by_id("t3_pain")
        self.assertIsNotNone(stored)
        self.assertTrue(stored["job_statement"])

    def test_the_corpus_is_indexed_for_hybrid_search(self):
        hits = self.deps.search_engine.search("invoice exports", limit=5)
        self.assertIn("t3_pain", {h.id for h in hits})

    def test_a_failing_store_is_recorded_instead_of_raising(self):
        class BrokenStore:
            def insert_opportunities(self, records):
                raise RuntimeError("disco lleno")

        state = {**self.state, "stored_ids": []}
        result = storage_node(
            state, RadarDependencies(fetcher=self.fetcher, store=BrokenStore())
        )
        self.assertTrue(any("disco lleno" in e for e in result["errors"]))


class TestQualityGateNode(OrchestrationTestCase):

    def test_the_cut_is_sixty_points(self):
        self.assertEqual(MIN_OPPORTUNITY_SCORE, 60.0)

    def test_pain_post_qualifies_under_a_reachable_cut(self):
        state = self.run_all_nodes(
            new_state(subreddit="smallbusiness"), min_score=REACHABLE_CUT
        )
        self.assertIn("t3_pain", {q["id"] for q in state["qualified"]})

    def test_signal_below_the_cut_is_rejected(self):
        state = self.run_all_nodes(
            new_state(subreddit="smallbusiness"), min_score=REACHABLE_CUT
        )
        qualified_ids = {q["id"] for q in state["qualified"]}
        for signal in state["signals"]:
            if signal.score_breakdown.final_score < REACHABLE_CUT:
                self.assertNotIn(signal.id, qualified_ids)

    def test_an_individual_signal_never_reaches_the_default_cut(self):
        """
        Caracteriza una propiedad real del sistema, no un deseo: con el scoring
        actual, ninguna señal aislada supera los 60 puntos, porque `spread` y
        `frequency` sólo crecen al agregar menciones de varias comunidades.
        Si algún día este test falla, es que la calibración cambió.
        """
        state = self.run_all_nodes(new_state(subreddit="smallbusiness"))
        self.assertEqual(state["qualified"], [])
        best = max(s.score_breakdown.final_score for s in state["signals"])
        self.assertLess(best, MIN_OPPORTUNITY_SCORE)

    def test_affiliate_risk_vetoes_a_signal_even_with_a_high_score(self):
        """El veto por riesgo no depende de la puntuacion."""
        state = new_state(subreddit="smallbusiness")
        state = self.run_all_nodes(state)

        # Se inyecta una senal de maxima puntuacion pero con riesgo de afiliado.
        from core.intelligence import IntelligenceEngine

        engine = IntelligenceEngine(use_transformers_if_available=False)
        tainted = engine.analyze_signal(
            item_id="t3_tainted",
            title=SPAM_POST["title"],
            body=SPAM_POST["selftext"],
            author=SPAM_POST["author"],
            subreddit=SPAM_POST["subreddit"],
            created_utc=SPAM_POST["created_utc"],
            url=SPAM_POST["url"],
        )
        tainted.score_breakdown.final_score = 99.0
        self.assertTrue(tainted.jtbd.risk_flags, "el post deberia traer riesgos")

        # min_score=0 aísla el veto: el único motivo posible de rechazo
        # es la bandera de riesgo, no la puntuación.
        result = quality_gate_node(
            {**state, "signals": [tainted]}, self.deps, min_score=0.0
        )
        self.assertNotIn("t3_tainted", {q["id"] for q in result["qualified"]})

    def test_qualified_entries_expose_score_and_statement(self):
        state = self.run_all_nodes(
            new_state(subreddit="smallbusiness"), min_score=REACHABLE_CUT
        )
        entry = [q for q in state["qualified"] if q["id"] == "t3_pain"][0]
        self.assertIn("opportunity_score", entry)
        self.assertIn("job_statement", entry)


class TestGraphCycle(OrchestrationTestCase):
    """El grafo es ciclico pero siempre termina."""

    def test_graph_compiles(self):
        self.assertIsNotNone(build_graph(self.deps))

    def test_graph_runs_end_to_end_and_qualifies(self):
        graph = build_graph(self.deps, min_score=REACHABLE_CUT)
        final = graph.invoke(new_state(subreddit="smallbusiness"))
        self.assertIn("t3_pain", {q["id"] for q in final["qualified"]})

    def test_graph_stores_even_what_the_gate_later_rejects(self):
        """El gate decide lo que se REPORTA, no lo que se GUARDA."""
        graph = build_graph(self.deps, min_score=99.0)
        final = graph.invoke(new_state(subreddit="smallbusiness"))
        self.assertEqual(final["qualified"], [])
        self.assertIn("t3_pain", final["stored_ids"])

    def test_graph_cycles_to_fetch_another_page_when_target_is_unmet(self):
        fetcher = FakeFetcher([[NOISE_POST], [PAIN_POST]])
        deps = RadarDependencies(
            fetcher=fetcher, store=self.store,
            search_engine=HybridSearchEngine(store=self.store),
        )
        graph = build_graph(
            deps, target_qualified=1, max_cycles=5, min_score=REACHABLE_CUT
        )
        final = graph.invoke(new_state(subreddit="smallbusiness"))

        self.assertGreaterEqual(len(fetcher.calls), 2, "deberia pedir 2a pagina")
        self.assertIn("t3_pain", {q["id"] for q in final["qualified"]})

    def test_cycle_stops_at_max_cycles(self):
        fetcher = FakeFetcher([[NOISE_POST]] * 50)
        deps = RadarDependencies(fetcher=fetcher, store=self.store)
        graph = build_graph(deps, target_qualified=99, max_cycles=3)
        final = graph.invoke(new_state(subreddit="smallbusiness"))

        self.assertLessEqual(final["cycle"], 3)
        self.assertLessEqual(len(fetcher.calls), 3)

    def test_lexical_index_survives_across_cycles(self):
        """
        Lo cosechado en el primer ciclo debe seguir siendo encontrable por la
        rama BM25 después del segundo. Si el índice se reemplazase en vez de
        extenderse, `t3_pain` perdería su rango léxico.

        La segunda página trae dos documentos que no mencionan "invoice": BM25
        asigna IDF negativo a un término presente en la mayoría del corpus, así
        que el término buscado tiene que ser raro para que puntúe.
        """
        page_two = [
            {**NOISE_POST, "id": "t3_other1",
             "title": "Deploying takes forever to finish",
             "selftext": "The release step is a tedious process every day."},
            {**NOISE_POST, "id": "t3_other2",
             "title": "I am drowning in support tickets",
             "selftext": "Answering them is a repetitive task that takes hours."},
        ]
        search_engine = HybridSearchEngine(store=self.store)
        deps = RadarDependencies(
            fetcher=FakeFetcher([[PAIN_POST], page_two]),
            store=self.store,
            search_engine=search_engine,
        )
        graph = build_graph(
            deps, target_qualified=99, max_cycles=2, min_score=REACHABLE_CUT
        )
        final = graph.invoke(new_state(subreddit="smallbusiness"))

        self.assertEqual(len(final["stored_ids"]), 3, "deberian entrar 3 documentos")

        hits = {h.id: h for h in search_engine.search("invoice", limit=5)}
        self.assertIn("t3_pain", hits)
        self.assertIsNotNone(
            hits["t3_pain"].bm25_rank, "deberia conservar su rango lexico"
        )

    def test_cycle_stops_when_the_source_is_exhausted(self):
        fetcher = FakeFetcher([[NOISE_POST]])
        deps = RadarDependencies(fetcher=fetcher, store=self.store)
        graph = build_graph(deps, target_qualified=99, max_cycles=10)
        graph.invoke(new_state(subreddit="smallbusiness"))
        self.assertEqual(len(fetcher.calls), 1, "sin cursor no hay que reintentar")


class TestPipeline(OrchestrationTestCase):

    def test_run_returns_the_qualified_opportunities(self):
        pipeline = RadarPipeline(deps=self.deps, min_score=REACHABLE_CUT)
        result = pipeline.run("smallbusiness", limit=10)
        self.assertIn("t3_pain", {q["id"] for q in result["qualified"]})

    def test_run_reports_both_tiers(self):
        """El resumen distingue señales sueltas de oportunidades consolidadas."""
        result = RadarPipeline(deps=self.deps).run("smallbusiness", limit=10)
        self.assertIn("qualified", result)
        self.assertIn("qualified_clusters", result)
        self.assertIn("clusters", result)

    def test_run_state_exposes_what_persistence_needs(self):
        """El resumen descarta lo que hay que escribir en la base."""
        state = RadarPipeline(deps=self.deps).run_state("smallbusiness", limit=10)
        self.assertTrue(state.get("signals"))
        self.assertTrue(state.get("filtered_items"))

    def test_run_reports_statistics(self):
        result = RadarPipeline(deps=self.deps).run("smallbusiness", limit=10)
        self.assertIn("fetched", result["stats"])
        self.assertIn("stored", result["stats"])

    def test_qualified_opportunities_come_back_sorted_by_score(self):
        pipeline = RadarPipeline(deps=self.deps, min_score=0.0)
        scores = [
            q["opportunity_score"]
            for q in pipeline.run("smallbusiness", limit=10)["qualified"]
        ]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_arun_is_the_asynchronous_twin(self):
        pipeline = RadarPipeline(deps=self.deps, min_score=REACHABLE_CUT)
        result = asyncio.run(pipeline.arun("smallbusiness", limit=10))
        self.assertIn("t3_pain", {q["id"] for q in result["qualified"]})


class TestRedditFetcherAdapter(unittest.TestCase):
    """
    El adaptador que conecta el cliente real con la firma del grafo.

    Se inyecta un cliente falso: lo que se verifica aquí es la traducción de
    cursores, no la red.
    """

    class FakeClient:
        def __init__(self, pages):
            self.pages = list(pages)
            self.calls = []

        async def fetch_subreddit_page(self, subreddit, listing="hot",
                                       limit=25, after=None, **kwargs):
            self.calls.append({"subreddit": subreddit, "listing": listing,
                               "limit": limit, "after": after})
            return self.pages.pop(0) if self.pages else ([], None)

    def test_adapter_returns_the_cursor_from_the_client(self):
        from core.orchestration import RedditFetcher

        client = self.FakeClient([([], "t3_next")])
        _, cursor = RedditFetcher(client=client)("saas", limit=5, sort="new")
        self.assertEqual(cursor, "t3_next")

    def test_adapter_forwards_the_incoming_cursor(self):
        from core.orchestration import RedditFetcher

        client = self.FakeClient([([], None)])
        RedditFetcher(client=client)("saas", limit=5, sort="new", cursor="t3_prev")
        self.assertEqual(client.calls[0]["after"], "t3_prev")

    def test_adapter_forwards_the_listing_and_limit(self):
        from core.orchestration import RedditFetcher

        client = self.FakeClient([([], None)])
        RedditFetcher(client=client)("saas", limit=7, sort="top")
        self.assertEqual(client.calls[0]["listing"], "top")
        self.assertEqual(client.calls[0]["limit"], 7)

    def test_adapter_serializes_posts_into_plain_dicts(self):
        from core.orchestration import RedditFetcher
        from core.ingestion import CleanPost

        post = CleanPost(id="t3_x", subreddit="saas", title="t", selftext="b")
        client = self.FakeClient([([post], None)])
        items, _ = RedditFetcher(client=client)("saas", limit=1, sort="hot")
        self.assertIsInstance(items[0], dict)
        self.assertEqual(items[0]["id"], "t3_x")


class TestMcpTools(OrchestrationTestCase):
    """Las tres herramientas expuestas por MCP, probadas sin levantar stdio."""

    def setUp(self):
        super().setUp()
        from core.orchestration import mcp_server

        self.tools = mcp_server.build_tools(self.deps, gate_min_score=REACHABLE_CUT)

    def test_the_three_tools_are_exposed(self):
        self.assertEqual(
            set(self.tools), {"scan_subreddit", "search_pain_points",
                              "get_opportunity_details"}
        )

    def test_scan_subreddit_returns_qualified_opportunities(self):
        result = self.tools["scan_subreddit"]("smallbusiness", limit=10, sort="hot")
        self.assertIn("t3_pain", {q["id"] for q in result["qualified"]})

    def test_search_pain_points_finds_an_indexed_opportunity(self):
        self.tools["scan_subreddit"]("smallbusiness", limit=10, sort="hot")
        hits = self.tools["search_pain_points"]("invoice exports", min_score=0.0, limit=5)
        self.assertIn("t3_pain", {h["id"] for h in hits})

    def test_search_pain_points_honours_the_minimum_score(self):
        self.tools["scan_subreddit"]("smallbusiness", limit=10, sort="hot")
        hits = self.tools["search_pain_points"](
            "invoice exports", min_score=99.9, limit=5
        )
        self.assertEqual(hits, [])

    def test_get_opportunity_details_returns_the_full_synthesis(self):
        self.tools["scan_subreddit"]("smallbusiness", limit=10, sort="hot")
        detail = self.tools["get_opportunity_details"]("t3_pain")
        self.assertEqual(detail["id"], "t3_pain")
        self.assertIn("job_statement", detail)
        self.assertIn("opportunity_score", detail)

    def test_get_opportunity_details_of_unknown_id_reports_not_found(self):
        self.assertIsNone(self.tools["get_opportunity_details"]("no-existe"))

    def test_server_factory_registers_the_tools(self):
        import warnings

        from core.orchestration import mcp_server

        with warnings.catch_warnings():
            # El SDK de MCP emite un aviso propio de pydantic-settings al
            # construir el servidor; es ruido de la dependencia, no nuestro.
            warnings.simplefilter("ignore")
            server = mcp_server.create_server(self.deps)

        self.assertIsNotNone(server)
        registered = {tool.name for tool in asyncio.run(server.list_tools())}
        self.assertEqual(
            registered,
            {"scan_subreddit", "search_pain_points", "get_opportunity_details"},
        )


# =====================================================================
# Fase 6b: agregación de oportunidades (deuda D6)
# =====================================================================

# Texto que el motor reconoce como dolor severo, con disposición a pagar
# explícita y queja: los tres ejes que hacen subir la puntuación.
PAIN_BODY = (
    "The export is completely broken and it is frustrating. "
    "I would pay for a tool that fixes this manual invoice process."
)

# El mismo dolor pero sin disposición a pagar: 45 puntos en lugar de 60.
# Sirve para los casos donde hace falta una señal que NO roce el techo.
WEAK_BODY = (
    "The export is completely broken and it is frustrating. "
    "This manual invoice process wastes my time."
)


def _make_signal(engine, sid, subreddit, title, body=PAIN_BODY,
                 created=4102444800.0):
    return engine.analyze_signal(
        item_id=sid,
        title=title,
        body=body,
        author=f"u/{sid}",
        subreddit=subreddit,
        created_utc=created,
        url=f"https://reddit.com/{sid}",
    )


class AggregationTestCase(unittest.TestCase):
    """Base con un motor de inteligencia compartido, que no es barato de crear."""

    @classmethod
    def setUpClass(cls):
        from core.intelligence import IntelligenceEngine

        cls.engine = IntelligenceEngine(use_transformers_if_available=False)

    def signal(self, sid, subreddit, title, **kwargs):
        return _make_signal(self.engine, sid, subreddit, title, **kwargs)

    def widespread_signals(self):
        """El mismo dolor, en cinco comunidades distintas."""
        return [
            self.signal(f"t3_{i}", sub, "Manual invoice export is broken")
            for i, sub in enumerate(
                ["smallbusiness", "SaaS", "accounting", "freelance", "bookkeeping"]
            )
        ]


class TestThresholdSeparation(unittest.TestCase):
    """Dos umbrales distintos para dos preguntas distintas."""

    def test_signal_threshold_is_twenty(self):
        from core.orchestration import SIGNAL_THRESHOLD

        self.assertEqual(SIGNAL_THRESHOLD, 20.0)

    def test_cluster_threshold_is_sixty(self):
        from core.orchestration import OPPORTUNITY_CLUSTER_THRESHOLD

        self.assertEqual(OPPORTUNITY_CLUSTER_THRESHOLD, 60.0)

    def test_legacy_constant_still_points_at_the_cluster_cut(self):
        """MIN_OPPORTUNITY_SCORE era el corte de oportunidad: lo sigue siendo."""
        from core.orchestration import (
            MIN_OPPORTUNITY_SCORE,
            OPPORTUNITY_CLUSTER_THRESHOLD,
        )

        self.assertEqual(MIN_OPPORTUNITY_SCORE, OPPORTUNITY_CLUSTER_THRESHOLD)

    def test_the_signal_cut_is_below_the_cluster_cut(self):
        from core.orchestration import OPPORTUNITY_CLUSTER_THRESHOLD, SIGNAL_THRESHOLD

        self.assertLess(SIGNAL_THRESHOLD, OPPORTUNITY_CLUSTER_THRESHOLD)


class TestClusterGrouping(AggregationTestCase):
    """Qué señales cuentan como 'el mismo problema'."""

    def test_shared_keyword_and_intent_group_together(self):
        from core.orchestration.aggregation import build_clusters

        clusters = build_clusters(self.widespread_signals())
        self.assertEqual(len(clusters), 1, "el mismo dolor deberia ser un cluster")
        self.assertEqual(clusters[0].mention_count, 5)

    def test_unrelated_pain_stays_in_its_own_cluster(self):
        from core.orchestration.aggregation import build_clusters

        signals = [
            self.signal("t3_a", "smallbusiness", "Manual invoice export is broken"),
            self.signal(
                "t3_b", "devops", "Deploying takes forever to finish every day",
                body="The release step is a tedious process and it is slow.",
            ),
        ]
        clusters = build_clusters(signals)
        self.assertGreaterEqual(len(clusters), 2)

    def test_grouping_is_transitive(self):
        """A comparte con B, B comparte con C: los tres son el mismo problema."""
        from core.orchestration.aggregation import build_clusters

        signals = [
            self.signal("t3_a", "s1", "Manual export is broken"),
            self.signal("t3_b", "s2", "Manual invoice work is broken"),
            self.signal("t3_c", "s3", "Invoice reconciliation is broken"),
        ]
        clusters = build_clusters(signals)
        biggest = max(clusters, key=lambda c: c.mention_count)
        self.assertEqual(biggest.mention_count, 3)

    def test_empty_input_produces_no_clusters(self):
        from core.orchestration.aggregation import build_clusters

        self.assertEqual(build_clusters([]), [])

    def test_cluster_exposes_its_member_ids(self):
        from core.orchestration.aggregation import build_clusters

        cluster = build_clusters(self.widespread_signals())[0]
        self.assertEqual(len(cluster.signal_ids), 5)
        self.assertIn("t3_0", cluster.signal_ids)


class TestClusterMetrics(AggregationTestCase):
    """Las métricas agregadas son lo que hace escalar la puntuación."""

    def test_community_count_counts_distinct_subreddits(self):
        from core.orchestration.aggregation import build_clusters

        cluster = build_clusters(self.widespread_signals())[0]
        self.assertEqual(cluster.community_count, 5)

    def test_repeated_subreddit_raises_frequency_not_spread(self):
        from core.orchestration.aggregation import build_clusters

        signals = [
            self.signal(f"t3_{i}", "smallbusiness", "Manual invoice export is broken")
            for i in range(4)
        ]
        cluster = build_clusters(signals)[0]
        self.assertEqual(cluster.community_count, 1)
        self.assertEqual(cluster.mention_count, 4)
        self.assertAlmostEqual(cluster.metrics.average_mentions_per_community, 4.0)

    def test_newest_age_wins_for_recency(self):
        """Un problema con una mención reciente sigue estando vivo."""
        from core.orchestration.aggregation import build_clusters

        signals = [
            self.signal("t3_old", "s1", "Manual invoice export is broken",
                        created=1000000000.0),
            self.signal("t3_new", "s2", "Manual invoice export is broken",
                        created=4102444800.0),
        ]
        cluster = build_clusters(signals)[0]
        self.assertEqual(cluster.metrics.newest_age_days, 0.0)

    def test_representative_is_the_highest_scoring_signal(self):
        from core.orchestration.aggregation import build_clusters

        cluster = build_clusters(self.widespread_signals())[0]
        self.assertIn(cluster.representative_id, cluster.signal_ids)

    def test_risk_flags_are_inherited_from_members(self):
        from core.orchestration.aggregation import build_clusters

        tainted = self.signal(
            "t3_spam", "s9", "Manual invoice export is broken",
            body=PAIN_BODY + " Use my referral link with promo code SAVE20.",
        )
        cluster = build_clusters([tainted])[0]
        self.assertTrue(cluster.risk_flags)


class TestClusterScoring(AggregationTestCase):
    """La consolidación debe hacer escalar la puntuación de forma orgánica."""

    def test_a_lone_signal_reproduces_its_own_individual_score(self):
        """
        Coherencia con el motor: agregar una sola señal no puede cambiar su
        puntuación. Si este test falla, el agregador y la Fase 3 discrepan.
        """
        from core.orchestration.aggregation import build_clusters

        signal = self.signal("t3_solo", "smallbusiness", "Manual invoice export is broken")
        cluster = build_clusters([signal])[0]
        self.assertAlmostEqual(
            cluster.score_breakdown.final_score,
            signal.score_breakdown.final_score,
            places=2,
        )

    def test_a_typical_lone_signal_stays_below_the_cluster_cut(self):
        from core.orchestration import OPPORTUNITY_CLUSTER_THRESHOLD
        from core.orchestration.aggregation import build_clusters

        signal = self.signal("t3_solo", "smallbusiness",
                             "Manual invoice export is broken", body=WEAK_BODY)
        cluster = build_clusters([signal])[0]
        self.assertLess(
            cluster.score_breakdown.final_score, OPPORTUNITY_CLUSTER_THRESHOLD
        )

    def test_a_perfect_lone_signal_caps_exactly_at_the_cut(self):
        """
        El techo aritmético de una señal individual es exactamente 60: con
        `spread` y `frequency` en su mínimo (0.2 cada uno) solo quedan 10 de
        los 50 puntos que reparten, y hacen falta severidad, recencia y
        disposición a pagar PERFECTAS para llegar. Documenta por qué aplicar
        este corte a mensajes sueltos vaciaba el radar.
        """
        from core.orchestration.aggregation import build_clusters

        signal = self.signal("t3_perfect", "smallbusiness",
                             "Manual invoice export is broken", body=PAIN_BODY)
        cluster = build_clusters([signal])[0]
        self.assertAlmostEqual(cluster.score_breakdown.final_score, 60.0, places=1)
        self.assertAlmostEqual(cluster.score_breakdown.spread_factor, 0.2)
        self.assertAlmostEqual(cluster.score_breakdown.frequency_factor, 0.2)

    def test_five_communities_push_the_cluster_past_sixty(self):
        """El caso que justifica toda la deuda D6."""
        from core.orchestration import OPPORTUNITY_CLUSTER_THRESHOLD
        from core.orchestration.aggregation import build_clusters

        cluster = build_clusters(self.widespread_signals())[0]
        self.assertGreaterEqual(
            cluster.score_breakdown.final_score, OPPORTUNITY_CLUSTER_THRESHOLD
        )

    def test_spread_saturates_with_five_communities(self):
        from core.orchestration.aggregation import build_clusters

        cluster = build_clusters(self.widespread_signals())[0]
        self.assertAlmostEqual(cluster.score_breakdown.spread_factor, 1.0)

    def test_more_evidence_never_lowers_the_score(self):
        from core.orchestration.aggregation import build_clusters

        few = build_clusters(self.widespread_signals()[:2])[0]
        many = build_clusters(self.widespread_signals())[0]
        self.assertGreaterEqual(
            many.score_breakdown.final_score, few.score_breakdown.final_score
        )

    def test_qualified_cluster_earns_a_high_urgency_tier(self):
        from core.orchestration.aggregation import build_clusters

        cluster = build_clusters(self.widespread_signals())[0]
        self.assertIn(cluster.score_breakdown.urgency_tier, ("HIGH", "CRITICAL"))


class TestAggregationNode(OrchestrationTestCase):
    """El nodo que consolida, dentro del grafo."""

    @classmethod
    def setUpClass(cls):
        from core.intelligence import IntelligenceEngine

        cls.engine = IntelligenceEngine(use_transformers_if_available=False)

    def _widespread(self):
        return [
            _make_signal(self.engine, f"t3_{i}", sub,
                         "Manual invoice export is broken")
            for i, sub in enumerate(
                ["smallbusiness", "SaaS", "accounting", "freelance", "bookkeeping"]
            )
        ]

    def test_node_publishes_qualified_clusters(self):
        from core.orchestration.graph import aggregation_node

        state = {**new_state(subreddit="smallbusiness"),
                 "all_signals": self._widespread()}
        result = aggregation_node(state, self.deps)
        self.assertTrue(result["qualified_clusters"])

    def test_node_rejects_clusters_below_the_cut(self):
        from core.orchestration.graph import aggregation_node

        lone = [_make_signal(self.engine, "t3_solo", "smallbusiness",
                             "Manual invoice export is broken", body=WEAK_BODY)]
        result = aggregation_node({**new_state(subreddit="x"),
                                   "all_signals": lone}, self.deps)
        self.assertEqual(result["qualified_clusters"], [])
        self.assertEqual(len(result["clusters"]), 1,
                         "el cluster existe, simplemente no cualifica")

    def test_node_vetoes_a_cluster_carrying_affiliate_risk(self):
        from core.orchestration.graph import aggregation_node

        tainted = [
            _make_signal(self.engine, f"t3_{i}", sub,
                         "Manual invoice export is broken",
                         body=PAIN_BODY + " Use my referral link, promo code SAVE20.")
            for i, sub in enumerate(["a1", "b2", "c3", "d4", "e5"])
        ]
        result = aggregation_node({**new_state(subreddit="x"),
                                   "all_signals": tainted}, self.deps)
        self.assertEqual(result["qualified_clusters"], [],
                         "el riesgo veta tambien al cluster")

    def test_node_reports_cluster_statistics(self):
        from core.orchestration.graph import aggregation_node

        state = {**new_state(subreddit="x"), "all_signals": self._widespread()}
        result = aggregation_node(state, self.deps)
        self.assertIn("clusters", result["stats"])
        self.assertIn("qualified_clusters", result["stats"])

    def test_node_without_signals_is_harmless(self):
        from core.orchestration.graph import aggregation_node

        result = aggregation_node(new_state(subreddit="x"), self.deps)
        self.assertEqual(result["qualified_clusters"], [])


class TestTwoTierGraph(OrchestrationTestCase):
    """El grafo completo, con los dos umbrales operando a la vez."""

    def test_micro_signals_reach_the_feed(self):
        """Una señal individual limpia entra al almacén y al feed."""
        graph = build_graph(self.deps)
        final = graph.invoke(new_state(subreddit="smallbusiness"))
        self.assertIn("t3_pain", {q["id"] for q in final["qualified"]})

    def test_micro_signals_do_not_become_opportunities_on_their_own(self):
        graph = build_graph(self.deps)
        final = graph.invoke(new_state(subreddit="smallbusiness"))
        self.assertEqual(final["qualified_clusters"], [])

    def test_signals_accumulate_across_cycles_for_aggregation(self):
        second = {**PAIN_POST, "id": "t3_pain2"}
        deps = RadarDependencies(
            fetcher=FakeFetcher([[PAIN_POST], [second]]),
            store=self.store,
            search_engine=HybridSearchEngine(store=self.store),
        )
        graph = build_graph(deps, target_qualified=99, max_cycles=2)
        final = graph.invoke(new_state(subreddit="smallbusiness"))
        self.assertEqual(len(final["all_signals"]), 2,
                         "la agregacion necesita la cosecha completa")


if __name__ == "__main__":
    unittest.main()
