"""
Capa de Inteligencia, NLP y Scoring de Oportunidad (Reddit Intelligence Radar)
=============================================================================
Paquete central unificado que integra:
- Motor analítico modular basado en plantillas TOML (reddit-market-analyzer).
- Extracción de Jobs-To-Be-Done y detección de riesgos (pain-miner).
- Algoritmo de decaimiento temporal exponencial y ponderación multi-eje (painpoint-atlas).
- Clasificador local Zero-Shot basado en NLI sin coste de API (reddit-sentiment-zero-shot).
- Clustering semántico no supervisado y descubrimiento de tópicos emergentes (reddit-nlp-analytics).
"""

from .clustering import ClusteringResult, TopicCluster, TopicClusterer
from .engine import (
    AnalyzedSignal,
    ComprehensiveIntelligenceReport,
    IntelligenceEngine,
)
from .jtbd_analyzer import TASK_BY_INTENT, JTBDAnalyzer, JTBDRequirement
from .temporal_scoring import (
    OpportunityMetrics,
    TemporalScoreBreakdown,
    TemporalScorer,
)
from .zeroshot_nli import (
    INTENT_CANDIDATE_LABELS,
    PAIN_CANDIDATE_LABELS,
    SENTIMENT_CANDIDATE_LABELS,
    ZeroShotNLIClassifier,
    ZeroShotResult,
)

__all__ = [
    "INTENT_CANDIDATE_LABELS",
    "PAIN_CANDIDATE_LABELS",
    "SENTIMENT_CANDIDATE_LABELS",
    "TASK_BY_INTENT",
    "AnalyzedSignal",
    "ClusteringResult",
    "ComprehensiveIntelligenceReport",
    "IntelligenceEngine",
    "JTBDAnalyzer",
    "JTBDRequirement",
    "OpportunityMetrics",
    "TemporalScoreBreakdown",
    "TemporalScorer",
    "TopicCluster",
    "TopicClusterer",
    "ZeroShotNLIClassifier",
    "ZeroShotResult",
]
