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

from .graph import (
    DEFAULT_MAX_CYCLES,
    DEFAULT_TARGET_QUALIFIED,
    Fetcher,
    RadarDependencies,
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
    RadarState,
    new_state,
    signal_to_record,
)

__all__ = [
    # Estado y puente entre capas
    "RadarState",
    "new_state",
    "signal_to_record",
    "MIN_OPPORTUNITY_SCORE",
    "BLOCKING_RISK_FLAGS",
    # Grafo
    "build_graph",
    "RadarDependencies",
    "Fetcher",
    "fetch_node",
    "filter_node",
    "intelligence_node",
    "storage_node",
    "quality_gate_node",
    "DEFAULT_TARGET_QUALIFIED",
    "DEFAULT_MAX_CYCLES",
    # Ejecución
    "RadarPipeline",
    "RedditFetcher",
    "create_default_dependencies",
]
