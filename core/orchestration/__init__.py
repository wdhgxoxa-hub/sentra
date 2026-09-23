"""
Capa de Orquestación (Fase 5)
=============================

Cierra el ciclo funcional del Reddit Intelligence Radar: conecta ingesta,
inteligencia y almacenamiento en un pipeline único, lo gobierna con una
máquina de estados de LangGraph y lo expone por Model Context Protocol.

    FetchNode -> FilterNode -> IntelligenceNode -> StorageNode -> QualityGateNode
                      ^                                                  |
                      +------------- (objetivo no alcanzado) ------------+

Uso típico:

    from core.orchestration import RadarPipeline

    resultado = RadarPipeline().run("smallbusiness", limit=25)
    for oportunidad in resultado["qualified"]:
        print(oportunidad["opportunity_score"], oportunidad["job_statement"])

Como servidor MCP:

    python -m core.orchestration.mcp_server
"""

from .aggregation import (
    OpportunityCluster,
    aggregate_metrics,
    build_clusters,
    cluster_to_dict,
)
from .graph import (
    DEFAULT_MAX_CYCLES,
    DEFAULT_TARGET_QUALIFIED,
    Fetcher,
    RadarDependencies,
    aggregation_node,
    build_graph,
    fetch_node,
    filter_node,
    intelligence_node,
    quality_gate_node,
    storage_node,
)
from .pipeline import (
    RadarPipeline,
    RedditFetcher,
    create_default_dependencies,
)
from .state import (
    BLOCKING_RISK_FLAGS,
    MIN_OPPORTUNITY_SCORE,
    MIN_SIGNAL_SCORE,
    OPPORTUNITY_CLUSTER_THRESHOLD,
    SIGNAL_THRESHOLD,
    RadarState,
    new_state,
    signal_to_record,
)

__all__ = [
    "BLOCKING_RISK_FLAGS",
    "DEFAULT_MAX_CYCLES",
    "DEFAULT_TARGET_QUALIFIED",
    "MIN_OPPORTUNITY_SCORE",
    "MIN_SIGNAL_SCORE",
    "OPPORTUNITY_CLUSTER_THRESHOLD",
    "SIGNAL_THRESHOLD",
    "Fetcher",
    "OpportunityCluster",
    "RadarDependencies",
    "RadarPipeline",
    "RadarState",
    "RedditFetcher",
    "aggregate_metrics",
    "aggregation_node",
    "build_clusters",
    "build_graph",
    "cluster_to_dict",
    "create_default_dependencies",
    "fetch_node",
    "filter_node",
    "intelligence_node",
    "new_state",
    "quality_gate_node",
    "signal_to_record",
    "storage_node",
]
