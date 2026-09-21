"""
Máquina de Estados del Radar (LangGraph)
========================================

Orquesta el flujo completo como un grafo con estado:

    FetchNode -> FilterNode -> IntelligenceNode -> StorageNode -> QualityGateNode
                      ^                                                  |
                      +------------- (objetivo no alcanzado) ------------+

Dos decisiones de diseño sostienen todo lo demás:

1. **Dependencias inyectadas.** Los nodos no construyen su cliente de Reddit
   ni su almacén: los reciben en un `RadarDependencies`. Sin esto el grafo
   solo sería ejecutable contra la red real, y por tanto no sería testeable.

2. **Resiliencia por nodo.** Cada nodo atrapa sus propias excepciones y las
   anota en `state["errors"]`. Un subreddit caído degrada la cosecha, no
   tumba la ejecución.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from langgraph.graph import END, START, StateGraph

from core.ingestion import PainPointFilter
from core.intelligence import AnalyzedSignal, IntelligenceEngine
from core.storage import HybridSearchEngine, LanceDBStore

from .aggregation import build_clusters, cluster_to_dict
from .state import (
    BLOCKING_RISK_FLAGS,
    MIN_OPPORTUNITY_SCORE,
    OPPORTUNITY_CLUSTER_THRESHOLD,
    SIGNAL_THRESHOLD,
    RadarState,
    signal_to_record,
)

logger = logging.getLogger(__name__)

# Firma del fetcher inyectable:
#   (subreddit, limit, sort, cursor) -> (items, next_cursor)
Fetcher = Callable[..., Tuple[Sequence[Dict[str, Any]], Optional[str]]]

DEFAULT_TARGET_QUALIFIED = 10
DEFAULT_MAX_CYCLES = 5


@dataclass
class RadarDependencies:
    """
    Colaboradores del grafo.

    El filtro, el motor y el buscador se construyen la primera vez que se
    piden: instanciar el motor de inteligencia no es gratis y no todos los
    flujos lo necesitan.
    """

    fetcher: Fetcher
    store: LanceDBStore
    pain_filter: Optional[PainPointFilter] = None
    engine: Optional[IntelligenceEngine] = None
    search_engine: Optional[HybridSearchEngine] = None

    def get_filter(self) -> PainPointFilter:
        if self.pain_filter is None:
            self.pain_filter = PainPointFilter()
        return self.pain_filter

    def get_engine(self) -> IntelligenceEngine:
        if self.engine is None:
            self.engine = IntelligenceEngine()
        return self.engine

    def get_search_engine(self) -> HybridSearchEngine:
        if self.search_engine is None:
            self.search_engine = HybridSearchEngine(store=self.store)
        return self.search_engine


def _item_text(item: Dict[str, Any]) -> str:
    """Texto evaluable de un ítem, sea post (title+selftext) o comentario (body)."""
    title = str(item.get("title") or "")
    body = str(item.get("selftext") or item.get("body") or "")
    return f"{title}\n{body}".strip()


# --------------------------------------------------------------------------
# Nodos
# --------------------------------------------------------------------------

def fetch_node(state: RadarState, deps: RadarDependencies) -> Dict[str, Any]:
    """Trae una página de la fuente y avanza el cursor."""
    cycle = int(state.get("cycle", 0)) + 1
    try:
        items, next_cursor = deps.fetcher(
            state["subreddit"],
            state.get("limit", 25),
            state.get("sort", "hot"),
            cursor=state.get("cursor"),
        )
    except Exception as exc:
        logger.error("FetchNode: %s", exc)
        return {
            "raw_items": [],
            "cursor": None,
            "cycle": cycle,
            "errors": [f"fetch: {exc}"],
            "stats": {"fetch_errors": 1},
        }

    items = list(items)
    return {
        "raw_items": items,
        "cursor": next_cursor,
        "cycle": cycle,
        "stats": {"fetched": len(items)},
    }


def filter_node(state: RadarState, deps: RadarDependencies) -> Dict[str, Any]:
    """Descarta bots, spam de afiliados y ruido sin señal de dolor."""
    raw_items = state.get("raw_items") or []
    pain_filter = deps.get_filter()

    kept: List[Dict[str, Any]] = []
    errors: List[str] = []

    for item in raw_items:
        try:
            verdict = pain_filter.evaluate(
                text=_item_text(item), author=str(item.get("author", ""))
            )
            if verdict.passed:
                kept.append({**item, "matched_keywords": verdict.matched_keywords})
        except Exception as exc:
            logger.error("FilterNode (%s): %s", item.get("id"), exc)
            errors.append(f"filter[{item.get('id')}]: {exc}")

    dropped = len(raw_items) - len(kept)
    return {
        "filtered_items": kept,
        "errors": errors,
        "stats": {"filtered_out": dropped, "filtered_in": len(kept)},
    }


def intelligence_node(state: RadarState, deps: RadarDependencies) -> Dict[str, Any]:
    """Analiza cada ítem superviviente: NLI, JTBD y scoring temporal."""
    items = state.get("filtered_items") or []
    if not items:
        return {"signals": [], "stats": {"analyzed": 0}}

    engine = deps.get_engine()
    signals: List[AnalyzedSignal] = []
    errors: List[str] = []

    for item in items:
        try:
            signals.append(
                engine.analyze_signal(
                    item_id=str(item.get("id", "")),
                    title=str(item.get("title") or ""),
                    body=str(item.get("selftext") or item.get("body") or ""),
                    author=str(item.get("author", "[deleted]")),
                    subreddit=str(item.get("subreddit") or state.get("subreddit", "")),
                    created_utc=float(item.get("created_utc", 0.0) or 0.0),
                    url=item.get("url") or item.get("permalink"),
                    # Una señal individual es UNA voz en UNA comunidad. Pasar
                    # aquí el número de comunidades del lote inflaba su
                    # `spread` con contexto que no le pertenece: un mensaje
                    # suelto parecía difundido solo porque venía acompañado.
                    # La difusión real la mide `aggregation_node` sobre el
                    # problema consolidado, que es donde significa algo.
                    community_count=1,
                )
            )
        except Exception as exc:
            logger.error("IntelligenceNode (%s): %s", item.get("id"), exc)
            errors.append(f"intelligence[{item.get('id')}]: {exc}")

    return {
        "signals": signals,
        # `signals` se reemplaza en cada vuelta; `all_signals` acumula, que
        # es lo que necesita la agregación para ver el patrón completo.
        "all_signals": signals,
        "errors": errors,
        "stats": {"analyzed": len(signals)},
    }


def storage_node(state: RadarState, deps: RadarDependencies) -> Dict[str, Any]:
    """Persiste las señales como registros vectoriales e indexa el corpus."""
    signals = state.get("signals") or []
    if not signals:
        return {"stored_ids": [], "stats": {"stored": 0}}

    # Los votos de Reddit no sobreviven al análisis: se recuperan del ítem crudo.
    upvotes = {
        str(item.get("id", "")): int(item.get("score", 0) or 0)
        for item in (state.get("filtered_items") or [])
    }

    try:
        records = [
            signal_to_record(signal, raw_score=upvotes.get(signal.id, 0))
            for signal in signals
        ]
        deps.store.insert_opportunities(records)
    except Exception as exc:
        logger.error("StorageNode: %s", exc)
        return {
            "stored_ids": [],
            "errors": [f"storage: {exc}"],
            "stats": {"storage_errors": 1},
        }

    errors: List[str] = []
    try:
        # Se extiende el índice léxico, no se reemplaza: el grafo es cíclico y
        # `index_corpus` descartaría lo cosechado en las vueltas anteriores.
        deps.get_search_engine().extend_corpus(
            [record.model_dump(exclude={"vector"}) for record in records]
        )
    except Exception as exc:
        logger.error("StorageNode (indexado BM25): %s", exc)
        errors.append(f"index: {exc}")

    return {
        "stored_ids": [record.id for record in records],
        "errors": errors,
        "stats": {"stored": len(records)},
    }


def quality_gate_node(
    state: RadarState,
    deps: RadarDependencies,
    min_score: float = SIGNAL_THRESHOLD,
) -> Dict[str, Any]:
    """
    Filtro de higiene sobre la señal INDIVIDUAL.

    Decide qué quejas entran al feed de actividad, no qué merece producto:
    ese juicio lo emite `aggregation_node` sobre el problema consolidado.
    El corte por defecto es `SIGNAL_THRESHOLD` (20), alcanzable por un
    mensaje suelto; `OPPORTUNITY_CLUSTER_THRESHOLD` (60) no lo es.

    El veto por riesgo sí es independiente de la puntuación: una señal con
    patrón de afiliado no pasa ni con 99 puntos, porque el riesgo no es una
    penalización gradual sino una descalificación.
    """
    qualified: List[Dict[str, Any]] = []
    rejected = 0

    for signal in state.get("signals") or []:
        risks = set(signal.jtbd.risk_flags or [])
        if risks & BLOCKING_RISK_FLAGS:
            rejected += 1
            continue
        if signal.score_breakdown.final_score < min_score:
            rejected += 1
            continue

        qualified.append({
            "id": signal.id,
            "subreddit": signal.subreddit,
            "author": signal.author,
            "text": signal.text,
            "opportunity_score": signal.score_breakdown.final_score,
            "urgency_tier": signal.score_breakdown.urgency_tier,
            "buying_intent": signal.buying_intent,
            "pain_severity": signal.pain_severity,
            "job_statement": signal.jtbd.job_statement,
            "current_solution": signal.jtbd.current_solution,
            "workaround_detected": signal.jtbd.workaround_detected,
            "url": signal.jtbd.source_url,
        })

    return {
        "qualified": qualified,
        "stats": {"qualified": len(qualified), "rejected": rejected},
    }


def aggregation_node(
    state: RadarState,
    deps: RadarDependencies,
    cluster_threshold: float = OPPORTUNITY_CLUSTER_THRESHOLD,
) -> Dict[str, Any]:
    """
    Consolida la cosecha completa en problemas recurrentes y los cualifica.

    Aquí es donde el corte de 60 puntos tiene sentido: sobre un cluster,
    `spread` y `frequency` reflejan difusión y recurrencia reales, que es
    lo que la fórmula de scoring presupone.
    """
    signals = state.get("all_signals") or []
    if not signals:
        return {
            "clusters": [],
            "qualified_clusters": [],
            "stats": {"clusters": 0, "qualified_clusters": 0},
        }

    try:
        clusters = build_clusters(
            signals,
            scorer=deps.get_engine().temporal_scorer,
            pain_filter=deps.get_filter(),
        )
    except Exception as exc:
        logger.error("AggregationNode: %s", exc)
        return {
            "clusters": [],
            "qualified_clusters": [],
            "errors": [f"aggregation: {exc}"],
            "stats": {"aggregation_errors": 1},
        }

    qualified = [
        cluster
        for cluster in clusters
        if not (set(cluster.risk_flags) & BLOCKING_RISK_FLAGS)
        and cluster.score_breakdown.final_score >= cluster_threshold
    ]

    return {
        "clusters": [cluster_to_dict(c) for c in clusters],
        "qualified_clusters": [cluster_to_dict(c) for c in qualified],
        "stats": {
            "clusters": len(clusters),
            "qualified_clusters": len(qualified),
        },
    }


# --------------------------------------------------------------------------
# Construcción del grafo
# --------------------------------------------------------------------------

def build_graph(
    deps: RadarDependencies,
    target_qualified: int = DEFAULT_TARGET_QUALIFIED,
    max_cycles: int = DEFAULT_MAX_CYCLES,
    min_score: float = SIGNAL_THRESHOLD,
    cluster_threshold: float = OPPORTUNITY_CLUSTER_THRESHOLD,
):
    """
    Compila la máquina de estados.

    Args:
        deps: colaboradores inyectados.
        target_qualified: cuántas señales cualificadas bastan para parar.
        max_cycles: tope duro de vueltas. Es la garantía de terminación: sin
            él, una fuente inagotable de ruido mantendría el grafo girando.
        min_score: corte de higiene sobre la señal individual (0-100).
        cluster_threshold: corte de oportunidad sobre el problema agregado.
    """
    graph = StateGraph(RadarState)

    graph.add_node("fetch", lambda state: fetch_node(state, deps))
    graph.add_node("filter", lambda state: filter_node(state, deps))
    graph.add_node("intelligence", lambda state: intelligence_node(state, deps))
    graph.add_node("storage", lambda state: storage_node(state, deps))
    graph.add_node(
        "quality_gate", lambda state: quality_gate_node(state, deps, min_score)
    )
    graph.add_node(
        "aggregate", lambda state: aggregation_node(state, deps, cluster_threshold)
    )

    graph.add_edge(START, "fetch")
    graph.add_edge("fetch", "filter")
    graph.add_edge("filter", "intelligence")
    graph.add_edge("intelligence", "storage")
    graph.add_edge("storage", "quality_gate")
    graph.add_edge("quality_gate", "aggregate")

    def route(state: RadarState) -> str:
        """Decide si hay que dar otra vuelta o cerrar la ejecución."""
        if len(state.get("qualified") or []) >= target_qualified:
            return END
        if state.get("cursor") is None:
            return END
        if int(state.get("cycle", 0)) >= max_cycles:
            return END
        return "fetch"

    graph.add_conditional_edges("aggregate", route, {"fetch": "fetch", END: END})

    return graph.compile()
