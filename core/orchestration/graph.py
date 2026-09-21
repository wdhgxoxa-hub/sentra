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

from .state import (
    BLOCKING_RISK_FLAGS,
    MIN_OPPORTUNITY_SCORE,
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

    communities = {str(i.get("subreddit") or state.get("subreddit", "")) for i in items}

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
                    community_count=max(1, len(communities)),
                )
            )
        except Exception as exc:
            logger.error("IntelligenceNode (%s): %s", item.get("id"), exc)
            errors.append(f"intelligence[{item.get('id')}]: {exc}")

    return {
        "signals": signals,
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
    min_score: float = MIN_OPPORTUNITY_SCORE,
) -> Dict[str, Any]:
    """
    Aplica las reglas de corte: puntuación mínima y veto por riesgo.

    El veto es independiente de la puntuación: una señal con patrón de
    afiliado no se cualifica ni con 99 puntos, porque el riesgo no es una
    penalización gradual sino una descalificación.

    Nota de calibración: el corte por defecto (60) opera sobre una escala
    pensada para oportunidades *agregadas*. Una señal individual arrastra
    `spread` y `frequency` mínimos por construcción, así que rara vez lo
    alcanza. `min_score` permite calibrar sin tocar código.
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


# --------------------------------------------------------------------------
# Construcción del grafo
# --------------------------------------------------------------------------

def build_graph(
    deps: RadarDependencies,
    target_qualified: int = DEFAULT_TARGET_QUALIFIED,
    max_cycles: int = DEFAULT_MAX_CYCLES,
    min_score: float = MIN_OPPORTUNITY_SCORE,
):
    """
    Compila la máquina de estados.

    Args:
        deps: colaboradores inyectados.
        target_qualified: cuántas oportunidades cualificadas bastan para parar.
        max_cycles: tope duro de vueltas. Es la garantía de terminación: sin
            él, una fuente inagotable de ruido mantendría el grafo girando.
        min_score: corte de cualificación sobre la escala 0-100.
    """
    graph = StateGraph(RadarState)

    graph.add_node("fetch", lambda state: fetch_node(state, deps))
    graph.add_node("filter", lambda state: filter_node(state, deps))
    graph.add_node("intelligence", lambda state: intelligence_node(state, deps))
    graph.add_node("storage", lambda state: storage_node(state, deps))
    graph.add_node(
        "quality_gate", lambda state: quality_gate_node(state, deps, min_score)
    )

    graph.add_edge(START, "fetch")
    graph.add_edge("fetch", "filter")
    graph.add_edge("filter", "intelligence")
    graph.add_edge("intelligence", "storage")
    graph.add_edge("storage", "quality_gate")

    def route(state: RadarState) -> str:
        """Decide si hay que dar otra vuelta o cerrar la ejecución."""
        if len(state.get("qualified") or []) >= target_qualified:
            return END
        if state.get("cursor") is None:
            return END
        if int(state.get("cycle", 0)) >= max_cycles:
            return END
        return "fetch"

    graph.add_conditional_edges("quality_gate", route, {"fetch": "fetch", END: END})

    return graph.compile()
