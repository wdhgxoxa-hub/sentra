"""
Núcleo Central de Inteligencia, NLP y Scoring de Oportunidades
=============================================================
Construido sobre:
1. Arquitectura base de reddit-market-analyzer con configuración desacoplada en TOML.
2. Extracción de Jobs-To-Be-Done y riesgos de pain-miner (jtbd_analyzer.py).
3. Ponderación y decaimiento temporal exponencial de painpoint-atlas (temporal_scoring.py).
4. Clasificación Zero-Shot local NLI de reddit-sentiment-zero-shot (zeroshot_nli.py).
5. Clustering semántico y descubrimiento de tópicos emergentes de reddit-nlp-analytics (clustering.py).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
import toml
from pydantic import BaseModel, Field

from .clustering import ClusteringResult, TopicClusterer
from .jtbd_analyzer import JTBDAnalyzer, JTBDRequirement
from .temporal_scoring import OpportunityMetrics, TemporalScoreBreakdown, TemporalScorer
from .zeroshot_nli import ZeroShotNLIClassifier, ZeroShotResult

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(r"F:\reddit_intelligence_radar\config\prompts.toml")


class AnalyzedSignal(BaseModel):
    """Señal analizada con enriquecimiento semántico, temporal y JTBD."""
    id: str
    text: str
    author: str
    subreddit: str
    created_utc: float
    # Clasificación Zero-Shot
    buying_intent: str
    intent_confidence: float
    pain_severity: str
    pain_confidence: float
    sentiment: str
    # JTBD y riesgos
    jtbd: JTBDRequirement
    # Puntuación temporal
    temporal_metrics: OpportunityMetrics
    score_breakdown: TemporalScoreBreakdown


class ComprehensiveIntelligenceReport(BaseModel):
    """Informe consolidado de inteligencia de mercado sobre una comunidad o temática."""
    topic_or_subreddit: str
    total_signals_evaluated: int
    critical_opportunities_count: int
    signals: List[AnalyzedSignal] = Field(default_factory=list)
    clusters: ClusteringResult
    emerging_keywords: List[Tuple[str, float]] = Field(default_factory=list)
    top_jtbd_statements: List[str] = Field(default_factory=list)


class IntelligenceEngine:
    """
    Motor orquestador de Inteligencia Artificial y Minería Semántica de Reddit.
    Combina modelos locales Zero-Shot, clustering no supervisado, formulación JTBD
    y algoritmos matemáticos de scoring temporal.
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        half_life_days: float = 180.0,
        model_name: str = "facebook/bart-large-mnli",
        use_transformers_if_available: bool = True
    ) -> None:
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.prompts = self._load_prompts()

        # Componentes analíticos especializados
        self.jtbd_analyzer = JTBDAnalyzer()
        self.temporal_scorer = TemporalScorer(half_life_days=half_life_days)
        self.zeroshot_classifier = ZeroShotNLIClassifier(
            model_name=model_name,
            use_transformers_if_available=use_transformers_if_available
        )
        self.clusterer = TopicClusterer()

    def _load_prompts(self) -> Dict[str, Any]:
        """Carga las plantillas maestras en TOML o inicializa fallbacks internos."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return toml.load(f)
            except Exception as e:
                logger.warning(f"Error cargando {self.config_path}: {e}")
        return {}

    def analyze_signal(
        self,
        item_id: str,
        title: str,
        body: str,
        author: str,
        subreddit: str,
        created_utc: float,
        url: Optional[str] = None,
        community_count: int = 1
    ) -> AnalyzedSignal:
        """
        Ejecuta el pipeline multi-eje completo sobre un post o comentario individual.
        """
        full_text = f"{title}\n{body}".strip()

        # 1. Inferencia Zero-Shot NLI
        intent_res: ZeroShotResult = self.zeroshot_classifier.classify_buying_intent(full_text)
        pain_res: ZeroShotResult = self.zeroshot_classifier.classify_pain_severity(full_text)
        sent_res: ZeroShotResult = self.zeroshot_classifier.classify_sentiment(full_text)

        # 2. Formulación JTBD y Riesgos
        jtbd_req: JTBDRequirement = self.jtbd_analyzer.analyze_post(
            post_id=item_id,
            title=title,
            body=body,
            url=url
        )

        # 3. Métricas para el Scorer Temporal
        age_days = self.temporal_scorer.calculate_age_days(created_utc)

        # Mapeo de severidad cualitativa a numérica (1.0 a 5.0)
        sev_map = {
            "severe blocker": 5.0,
            "time consuming friction": 3.5,
            "minor inconvenience": 2.0,
            "no problem": 1.0
        }
        num_severity = sev_map.get(pain_res.predicted_label, 2.5)

        # Mapeo de disposición a pagar (0.0 a 3.0)
        paid_map = {
            "explicit": 3.0,
            "implicit": 1.5,
            "none": 0.0
        }
        num_paid = paid_map.get(jtbd_req.willingness_to_pay, 0.0)

        metrics = OpportunityMetrics(
            mention_count=1,
            community_count=community_count,
            average_mentions_per_community=1.0,
            average_severity=num_severity,
            average_paid_signal=num_paid,
            newest_age_days=age_days
        )

        # 4. Cálculo del puntaje temporal
        score_breakdown = self.temporal_scorer.score(metrics)

        return AnalyzedSignal(
            id=item_id,
            text=full_text,
            author=author,
            subreddit=subreddit,
            created_utc=created_utc,
            buying_intent=intent_res.predicted_label,
            intent_confidence=intent_res.confidence,
            pain_severity=pain_res.predicted_label,
            pain_confidence=pain_res.confidence,
            sentiment=sent_res.predicted_label,
            jtbd=jtbd_req,
            temporal_metrics=metrics,
            score_breakdown=score_breakdown
        )

    def analyze_batch(
        self,
        items: Sequence[Dict[str, Any]],
        topic_or_subreddit: str = "General",
        n_clusters: Optional[int] = None
    ) -> ComprehensiveIntelligenceReport:
        """
        Analiza un lote de publicaciones y comentarios:
        - Aplica scoring individual e inferencia Zero-Shot a cada uno.
        - Agrupa semánticamente los textos mediante TopicClusterer.
        - Extrae palabras clave emergentes (TF-IDF).
        - Sintetiza los requerimientos JTBD de mayor urgencia.
        """
        analyzed_signals: List[AnalyzedSignal] = []
        all_texts: List[str] = []

        # Contar comunidades únicas para el factor de dispersión
        unique_communities = {item.get("subreddit", topic_or_subreddit) for item in items}
        comm_count = max(1, len(unique_communities))

        for it in items:
            item_id = str(it.get("id", ""))
            title = str(it.get("title", ""))
            body = str(it.get("selftext") or it.get("body") or "")
            author = str(it.get("author", "[deleted]"))
            sub = str(it.get("subreddit", topic_or_subreddit))
            created_utc = float(it.get("created_utc", 0.0))
            url = it.get("permalink") or it.get("url")

            signal = self.analyze_signal(
                item_id=item_id,
                title=title,
                body=body,
                author=author,
                subreddit=sub,
                created_utc=created_utc,
                url=url,
                community_count=comm_count
            )
            analyzed_signals.append(signal)
            all_texts.append(signal.text)

        # Clustering y palabras clave emergentes
        clustering_res = self.clusterer.cluster(all_texts, n_clusters=n_clusters)
        emerging_kws = self.clusterer.extract_emerging_keywords(all_texts, top_n=15)

        # Filtrar oportunidades críticas (score >= 60.0 o urgencia alta)
        critical_count = sum(
            1 for s in analyzed_signals
            if s.score_breakdown.urgency_tier in ("CRITICAL", "HIGH")
        )

        # Top JTBD statements
        sorted_signals = sorted(
            analyzed_signals,
            key=lambda s: s.score_breakdown.final_score,
            reverse=True
        )
        top_jtbds = [
            s.jtbd.job_statement
            for s in sorted_signals[:5]
            if s.jtbd.job_statement
        ]

        return ComprehensiveIntelligenceReport(
            topic_or_subreddit=topic_or_subreddit,
            total_signals_evaluated=len(analyzed_signals),
            critical_opportunities_count=critical_count,
            signals=sorted_signals,
            clusters=clustering_res,
            emerging_keywords=emerging_kws,
            top_jtbd_statements=top_jtbds
        )
