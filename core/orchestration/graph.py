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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, START, StateGraph

from core.ingestion import PainPointFilter
from core.ingestion.errors import RedditAccessError
from core.intelligence import AnalyzedSignal, IntelligenceEngine
from core.storage import HybridSearchEngine, LanceDBStore

from .aggregation import build_clusters, cluster_to_dict
from .state import (
    BLOCKING_RISK_FLAGS,
    MIN_OPPORTUNITY_SCORE,
    MIN_SIGNAL_SCORE,
    RadarState,
    signal_to_record,
)
from .top_n import rank_top, run_outcome, stop_reason

logger = logging.getLogger(__name__)

# Firma del fetcher inyectable:
#   (subreddit, limit, sort, cursor) -> (items, next_cursor)
Fetcher = Callable[..., tuple[Sequence[dict[str, Any]], str | None]]

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
    pain_filter: PainPointFilter | None = None
    engine: IntelligenceEngine | None = None
    search_engine: HybridSearchEngine | None = None

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


def data_source_of(fetcher: Any) -> str:
    """Fuente de los datos que entrega `fetcher`: "reddit" o "demo" (D-J).

    Es el único sitio que lo decide: la ejecución en PostgreSQL y cada fila
    de LanceDB lo leen de aquí, así no pueden discrepar.
    """
    return "reddit" if type(fetcher).__name__ == "RedditFetcher" else "demo"


def _item_text(item: dict[str, Any]) -> str:
    """Texto evaluable de un ítem, sea post (title+selftext) o comentario (body)."""
    title = str(item.get("title") or "")
    body = str(item.get("selftext") or item.get("body") or "")
    return f"{title}\n{body}".strip()


# --------------------------------------------------------------------------
# Nodos
# --------------------------------------------------------------------------

def _fetch_failure(
    cycle: int, code: str, message: str, retry_after: int | None = None
) -> dict[str, Any]:
    """Resultado de un fetch que no pudo traer datos: la ejecución FALLA."""
    logger.error("FetchNode [%s]: %s", code, message)
    return {
        "raw_items": [],
        "cursor": None,
        "cycle": cycle,
        "errors": [f"fetch: {code}: {message}"],
        "stats": {"fetch_errors": 1},
        "failure": {
            "code": code,
            "message": message,
            "retryAfterSeconds": retry_after,
        },
    }


def fetch_node(state: RadarState, deps: RadarDependencies) -> dict[str, Any]:
    """
    Trae una página de la fuente y avanza el cursor.

    Si la fuente no entrega datos, la ejecución falla con un motivo tipado
    (`failure`). Una página vacía solo es la que la fuente devolvió vacía.
    """
    cycle = int(state.get("cycle", 0)) + 1
    try:
        items, next_cursor = deps.fetcher(
            state["subreddit"],
            state.get("limit", 25),
            state.get("sort", "hot"),
            cursor=state.get("cursor"),
        )
    except RedditAccessError as exc:
        return _fetch_failure(
            cycle, exc.code, str(exc), getattr(exc, "retry_after_seconds", None)
        )
    # Frontera con un fetcher inyectable: cualquier otro fallo también debe
    # terminar en un fallo explícito de la ejecución, nunca en una página vacía.
    except Exception as exc:  # noqa: BLE001
        return _fetch_failure(cycle, "fetch_failed", f"{type(exc).__name__}: {exc}")

    items = list(items)
    return {
        "raw_items": items,
        "cursor": next_cursor,
        "cycle": cycle,
        "stats": {"fetched": len(items)},
    }


def filter_node(state: RadarState, deps: RadarDependencies) -> dict[str, Any]:
    """Descarta bots, spam de afiliados y ruido sin señal de dolor."""
    raw_items = state.get("raw_items") or []
    pain_filter = deps.get_filter()

    kept: list[dict[str, Any]] = []
    errors: list[str] = []

    for item in raw_items:
        try:
            verdict = pain_filter.evaluate(
                text=_item_text(item), author=str(item.get("author", ""))
            )
            if verdict.passed:
                kept.append({**item, "matched_keywords": verdict.matched_keywords})
        # Resiliencia por item (ver cabecera): un post que rompe el filtro se
        # anota en `errors` y no tumba el resto de la pagina.
        except Exception as exc:  # noqa: BLE001
            logger.error("FilterNode (%s): %s", item.get("id"), exc)
            errors.append(f"filter[{item.get('id')}]: {exc}")

    dropped = len(raw_items) - len(kept)
    return {
        "filtered_items": kept,
        # La cosecha acumulada entre ciclos, que es la que se persiste.
        "all_items": kept,
        "errors": errors,
        "stats": {"filtered_out": dropped, "filtered_in": len(kept)},
    }


def comments_node(state: RadarState, deps: RadarDependencies) -> dict[str, Any]:
    """Trae los comentarios de los posts que pasaron el filtro (D-I).

    Solo si la fuente sabe hacerlo (`fetch_comments`); el corpus de
    demostración no tiene comentarios. Los límites (cuántos por post, qué
    profundidad) los aplica la fuente. Cada comentario pasa el mismo filtro
    que los posts: todos se guardan como crudos, solo los que lo superan se
    analizan. Un hilo que falla no tumba la ejecución: los posts ya están.
    """
    traer = getattr(deps.fetcher, "fetch_comments", None)
    if not callable(traer):
        return {"comment_items": [], "all_comments": []}

    pain_filter = deps.get_filter()
    subreddit = state["subreddit"]
    traidos: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    errors: list[str] = []

    for post in state.get("filtered_items") or []:
        try:
            comentarios = list(traer(subreddit, str(post.get("id", ""))))
        except RedditAccessError as exc:
            logger.warning("CommentsNode (%s): %s", post.get("id"), exc)
            errors.append(f"comments[{post.get('id')}]: {exc.code}")
            continue
        for comentario in comentarios:
            traidos.append(comentario)
            verdict = pain_filter.evaluate(
                text=_item_text(comentario), author=str(comentario.get("author", ""))
            )
            if verdict.passed:
                kept.append({**comentario, "matched_keywords": verdict.matched_keywords})

    return {
        "comment_items": kept,
        "all_comments": traidos,
        "errors": errors,
        "stats": {"comments_fetched": len(traidos), "comments_kept": len(kept)},
    }


def intelligence_node(state: RadarState, deps: RadarDependencies) -> dict[str, Any]:
    """Analiza cada ítem superviviente: NLI, JTBD y scoring temporal."""
    items = [*(state.get("filtered_items") or []), *(state.get("comment_items") or [])]
    if not items:
        return {"signals": [], "stats": {"analyzed": 0}}

    engine = deps.get_engine()
    signals: list[AnalyzedSignal] = []
    errors: list[str] = []

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
        # Resiliencia por item: un analisis fallido se anota y el lote sigue.
        except Exception as exc:  # noqa: BLE001
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


def storage_node(state: RadarState, deps: RadarDependencies) -> dict[str, Any]:
    """Persiste las señales como registros vectoriales e indexa el corpus."""
    signals = state.get("signals") or []
    if not signals:
        return {"stored_ids": [], "stats": {"stored": 0}}

    # Los votos de Reddit no sobreviven al análisis: se recuperan del ítem crudo.
    upvotes = {
        str(item.get("id", "")): int(item.get("score", 0) or 0)
        for item in [*(state.get("filtered_items") or []), *(state.get("comment_items") or [])]
    }

    try:
        records = [
            signal_to_record(
                signal,
                raw_score=upvotes.get(signal.id, 0),
                data_source=data_source_of(deps.fetcher),
            )
            for signal in signals
        ]
        deps.store.insert_opportunities(records)
    # Frontera con LanceDB: cualquier fallo del almacen se anota en `errors`.
    except Exception as exc:  # noqa: BLE001
        logger.error("StorageNode: %s", exc)
        return {
            "stored_ids": [],
            "errors": [f"storage: {exc}"],
            "stats": {"storage_errors": 1},
        }

    errors: list[str] = []
    try:
        # Se extiende el índice léxico, no se reemplaza: el grafo es cíclico y
        # `index_corpus` descartaría lo cosechado en las vueltas anteriores.
        deps.get_search_engine().extend_corpus(
            [record.model_dump(exclude={"vector"}) for record in records]
        )
    # El indice lexico es secundario: si falla, la busqueda densa sigue.
    except Exception as exc:  # noqa: BLE001
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
    min_score: float = MIN_SIGNAL_SCORE,
) -> dict[str, Any]:
    """
    Filtro de higiene sobre la señal INDIVIDUAL.

    Decide qué quejas entran al feed de actividad, no qué merece producto:
    ese juicio lo emite `aggregation_node` sobre el problema consolidado.
    El corte por defecto es `MIN_SIGNAL_SCORE` (20), alcanzable por un
    mensaje suelto; `MIN_OPPORTUNITY_SCORE` (60) no lo es.

    El veto por riesgo sí es independiente de la puntuación: una señal con
    patrón de afiliado no pasa ni con 99 puntos, porque el riesgo no es una
    penalización gradual sino una descalificación.
    """
    qualified: list[dict[str, Any]] = []
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


def _con_ranking(
    state: RadarState,
    clusters: list[dict[str, Any]],
    qualified: list[dict[str, Any]],
    max_cycles: int,
) -> dict[str, Any]:
    """
    Marca el Top N y calcula el resultado explícito de la ejecución (AUD-007).

    `top_rank` (1..TOP_N) solo lo llevan las cualificadas que entran en el
    ranking; el resto queda en None. El resultado se calcula con el mismo
    criterio de parada que usa el grafo, así que el de la última vuelta es
    el de la ejecución.
    """
    posiciones = {c["key"]: i for i, c in enumerate(rank_top(qualified), start=1)}
    for cluster in [*clusters, *qualified]:
        cluster["top_rank"] = posiciones.get(cluster["key"])
    motivo = stop_reason({**state, "qualified_clusters": qualified}, max_cycles)
    return {
        "clusters": clusters,
        "qualified_clusters": qualified,
        "top": run_outcome(qualified, len(clusters), motivo),
    }


def aggregation_node(
    state: RadarState,
    deps: RadarDependencies,
    cluster_threshold: float = MIN_OPPORTUNITY_SCORE,
    max_cycles: int = DEFAULT_MAX_CYCLES,
) -> dict[str, Any]:
    """
    Consolida la cosecha completa en problemas recurrentes y los cualifica.

    Aquí es donde el corte de 60 puntos tiene sentido: sobre un cluster,
    `spread` y `frequency` reflejan difusión y recurrencia reales, que es
    lo que la fórmula de scoring presupone. También fija el Top N y el
    resultado de la ejecución.
    """
    signals = state.get("all_signals") or []
    if not signals:
        return {
            **_con_ranking(state, [], [], max_cycles),
            "stats": {"clusters": 0, "qualified_clusters": 0},
        }

    try:
        clusters = build_clusters(
            signals,
            scorer=deps.get_engine().temporal_scorer,
            pain_filter=deps.get_filter(),
        )
    # Resiliencia por nodo: un fallo al agrupar se anota y no pierde la cosecha.
    except Exception as exc:  # noqa: BLE001
        logger.error("AggregationNode: %s", exc)
        return {
            **_con_ranking(state, [], [], max_cycles),
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
        **_con_ranking(
            state,
            [cluster_to_dict(c) for c in clusters],
            [cluster_to_dict(c) for c in qualified],
            max_cycles,
        ),
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
    max_cycles: int = DEFAULT_MAX_CYCLES,
    min_score: float = MIN_SIGNAL_SCORE,
    cluster_threshold: float = MIN_OPPORTUNITY_SCORE,
):
    """
    Compila la máquina de estados.

    Se detiene al reunir TOP_N problemas cualificados, al agotarse la fuente,
    al fallar el acceso o al llegar a `max_cycles` (ver `top_n.stop_reason`);
    nunca por número de señales.

    Args:
        deps: colaboradores inyectados.
        max_cycles: tope duro de vueltas. Es la garantía de terminación: sin
            él, una fuente inagotable de ruido mantendría el grafo girando.
        min_score: corte de higiene sobre la señal individual (0-100).
        cluster_threshold: corte de oportunidad sobre el problema agregado.
    """
    graph = StateGraph(RadarState)

    graph.add_node("fetch", lambda state: fetch_node(state, deps))
    graph.add_node("filter", lambda state: filter_node(state, deps))
    graph.add_node("comments", lambda state: comments_node(state, deps))
    graph.add_node("intelligence", lambda state: intelligence_node(state, deps))
    graph.add_node("storage", lambda state: storage_node(state, deps))
    graph.add_node(
        "quality_gate", lambda state: quality_gate_node(state, deps, min_score)
    )
    graph.add_node(
        "aggregate",
        lambda state: aggregation_node(state, deps, cluster_threshold, max_cycles),
    )

    graph.add_edge(START, "fetch")
    graph.add_edge("fetch", "filter")
    graph.add_edge("filter", "comments")
    graph.add_edge("comments", "intelligence")
    graph.add_edge("intelligence", "storage")
    graph.add_edge("storage", "quality_gate")
    graph.add_edge("quality_gate", "aggregate")

    def route(state: RadarState) -> str:
        """Decide si hay que dar otra vuelta o cerrar la ejecución."""
        return END if stop_reason(state, max_cycles) is not None else "fetch"

    graph.add_conditional_edges("aggregate", route, {"fetch": "fetch", END: END})

    return graph.compile()
