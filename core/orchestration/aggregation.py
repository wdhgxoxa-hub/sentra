"""
Agregación de Oportunidades (resolución de la deuda D6)
=======================================================

El problema que resuelve
------------------------
El scoring de la Fase 3 pondera cinco factores:

    spread .25 | frequency .25 | severity .20 | recency .15 | paid .15

`spread` mide en cuántas comunidades aparece un problema y `frequency`
cuántas veces se repite. Una señal individual los tiene clavados en el
mínimo (1/5 = 0.2 cada uno), de modo que aporta como mucho 10 de los 50
puntos que reparten entre ambos. Su techo aritmético es exactamente 60, y
solo si severidad, recencia y disposición a pagar son perfectas a la vez.
Por eso el corte de 60 rechazaba absolutamente todo.

La causa no era el umbral: era aplicarlo al objeto equivocado. El scoring
está calibrado para **oportunidades**, no para mensajes sueltos.

La solución
-----------
Dos umbrales para dos preguntas distintas:

- `SIGNAL_THRESHOLD` (20): ¿esta queja merece entrar al almacén y al feed
  de actividad? Es un filtro de higiene sobre el mensaje individual.
- `OPPORTUNITY_CLUSTER_THRESHOLD` (60): ¿este problema recurrente merece
  que alguien construya producto? Se aplica al **cluster agregado**.

Al consolidar señales que apuntan al mismo problema, `spread` y `frequency`
crecen de verdad y las oportunidades reales escalan solas a 60-90 puntos,
que es justo lo que la fórmula presupone.

Cómo se agrupa
--------------
Dos señales pertenecen al mismo problema si comparten la misma intención
JTBD y al menos un término de dolor del vocabulario de dominio. La relación
se cierra por transitividad (union-find): si A comparte con B y B con C,
los tres describen el mismo problema.

Es deliberadamente léxico y determinista, no un KMeans: un cluster que
decide el gasto de un equipo de producto tiene que poder explicarse con la
frase "estas cinco personas dijeron 'invoice' y 'manual' en cinco foros
distintos".
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from core.intelligence import OpportunityMetrics, TemporalScorer
from core.intelligence.zeroshot_nli import UNDETERMINED_LABEL

logger = logging.getLogger(__name__)

# Mismos mapeos que aplica IntelligenceEngine.analyze_signal. Se replican
# aquí en forma de constante, y un test comprueba que agregar una señal
# sola reproduce su puntuación individual: si el motor cambiara su escala
# sin avisar, esa prueba falla.
SEVERITY_SCALE: dict[str, float] = {
    "severe blocker": 5.0,
    "time consuming friction": 3.5,
    "minor inconvenience": 2.0,
    "no problem": 1.0,
    # Sin evidencia la severidad aporta cero al cluster (AUD-005).
    UNDETERMINED_LABEL: 1.0,
}
DEFAULT_SEVERITY = 2.5

PAID_SIGNAL_SCALE: dict[str, float] = {
    "explicit": 3.0,
    "implicit": 1.5,
    "none": 0.0,
}

# Cuántas citas literales se conservan por cluster para la ficha de detalle.
MAX_EVIDENCE_QUOTES = 5


class OpportunityCluster(BaseModel):
    """Un problema recurrente, con las señales que lo sostienen."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    key: str
    label: str
    intent_type: str
    keywords: list[str] = Field(default_factory=list)

    signal_ids: list[str] = Field(default_factory=list)
    subreddits: list[str] = Field(default_factory=list)
    mention_count: int = 0
    community_count: int = 0

    representative_id: str = ""
    job_statement: str = ""
    current_solutions: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)

    metrics: OpportunityMetrics
    score_breakdown: Any
    evidence: list[dict[str, Any]] = Field(default_factory=list)


def signal_keywords(signal: Any, pain_filter: Any) -> list[str]:
    """Términos de dolor del vocabulario de dominio presentes en la señal."""
    try:
        return sorted(set(pain_filter.match_keywords(signal.text or "")))
    # `pain_filter` y `signal` llegan por duck typing: lo esperable es un
    # objeto sin la forma debida, no un fallo del regex.
    except (AttributeError, TypeError) as exc:
        logger.warning("No se pudieron extraer keywords de %s: %s", signal.id, exc)
        return []


def _group_indices(
    signals: Sequence[Any],
    keywords_by_index: dict[int, list[str]],
) -> list[list[int]]:
    """
    Agrupa por componentes conexas: misma intención más algún término común.

    Comparación por pares, O(n^2). Con lotes de cientos de señales es
    irrelevante; si algún día se agregan decenas de miles, habrá que
    indexar por término en lugar de comparar todo contra todo.
    """
    parent = list(range(len(signals)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(signals)):
        for j in range(i + 1, len(signals)):
            same_intent = (
                signals[i].jtbd.intent_type == signals[j].jtbd.intent_type
            )
            shares_term = bool(
                set(keywords_by_index[i]) & set(keywords_by_index[j])
            )
            if same_intent and shares_term:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for index in range(len(signals)):
        groups.setdefault(find(index), []).append(index)
    return list(groups.values())


def aggregate_metrics(signals: Sequence[Any]) -> OpportunityMetrics:
    """
    Consolida las métricas de un grupo de señales.

    Dos decisiones con consecuencias:

    - `newest_age_days` es el **mínimo**, no la media: un problema con una
      queja de ayer sigue vivo aunque las otras sean de hace un año.
    - `community_count` cuenta subreddits **distintos**. Diez quejas en un
      solo foro son un foro descontento; una queja en diez foros es un
      patrón de mercado. La fórmula ya distingue ambos casos, pero solo si
      se le dan los números correctos.
    """
    subreddits = {str(s.subreddit or "") for s in signals if s.subreddit}
    community_count = max(1, len(subreddits))
    mention_count = len(signals)

    severities = [
        SEVERITY_SCALE.get(s.pain_severity, DEFAULT_SEVERITY) for s in signals
    ]
    paid = [
        PAID_SIGNAL_SCALE.get(s.jtbd.willingness_to_pay, 0.0) for s in signals
    ]
    ages = [
        float(getattr(s.temporal_metrics, "newest_age_days", 0.0) or 0.0)
        for s in signals
    ]

    return OpportunityMetrics(
        mention_count=mention_count,
        community_count=community_count,
        average_mentions_per_community=mention_count / float(community_count),
        average_severity=sum(severities) / len(severities) if severities else DEFAULT_SEVERITY,
        average_paid_signal=sum(paid) / len(paid) if paid else 0.0,
        newest_age_days=min(ages) if ages else 0.0,
    )


def _cluster_label(signals: Sequence[Any], keywords: Sequence[str]) -> str:
    """Etiqueta legible del problema, a partir de sus términos y su foro."""
    if keywords:
        return " + ".join(list(keywords)[:3])
    return signals[0].subreddit or "problema sin etiquetar"


def build_clusters(
    signals: Sequence[Any],
    scorer: TemporalScorer | None = None,
    pain_filter: Any | None = None,
) -> list[OpportunityCluster]:
    """
    Consolida señales en oportunidades y las puntúa con métricas agregadas.

    Devuelve los clusters ordenados de mayor a menor puntuación.
    """
    signals = list(signals)
    if not signals:
        return []

    if pain_filter is None:
        from core.ingestion import PainPointFilter

        pain_filter = PainPointFilter()
    if scorer is None:
        scorer = TemporalScorer()

    keywords_by_index = {
        i: signal_keywords(s, pain_filter) for i, s in enumerate(signals)
    }

    clusters: list[OpportunityCluster] = []

    for group in _group_indices(signals, keywords_by_index):
        members = [signals[i] for i in group]
        metrics = aggregate_metrics(members)
        breakdown = scorer.score(metrics)

        # El representante es la señal individualmente más fuerte: es la que
        # mejor explica el problema cuando hay que enseñar solo una.
        representative = max(
            members, key=lambda s: s.score_breakdown.final_score
        )

        shared_keywords = sorted(
            set().union(*(set(keywords_by_index[i]) for i in group))
        )
        subreddits = sorted({str(s.subreddit) for s in members if s.subreddit})

        solutions = sorted({
            s.jtbd.current_solution for s in members if s.jtbd.current_solution
        })
        risks = sorted(set().union(
            *(set(s.jtbd.risk_flags or []) for s in members)
        )) if members else []

        evidence = [
            {
                "signal_id": s.id,
                "subreddit": s.subreddit,
                "author": s.author,
                "quote": (s.text or "")[:400],
                "url": s.jtbd.source_url,
                "score": s.score_breakdown.final_score,
            }
            for s in sorted(
                members, key=lambda s: s.score_breakdown.final_score, reverse=True
            )[:MAX_EVIDENCE_QUOTES]
        ]

        clusters.append(
            OpportunityCluster(
                key=f"{representative.jtbd.intent_type}:{'|'.join(shared_keywords[:4])}",
                label=_cluster_label(members, shared_keywords),
                intent_type=representative.jtbd.intent_type,
                keywords=shared_keywords,
                signal_ids=[s.id for s in members],
                subreddits=subreddits,
                mention_count=metrics.mention_count,
                community_count=metrics.community_count,
                representative_id=representative.id,
                job_statement=representative.jtbd.job_statement,
                current_solutions=solutions,
                risk_flags=risks,
                metrics=metrics,
                score_breakdown=breakdown,
                evidence=evidence,
            )
        )

    clusters.sort(key=lambda c: c.score_breakdown.final_score, reverse=True)
    return clusters


def cluster_to_dict(cluster: OpportunityCluster) -> dict[str, Any]:
    """Aplana un cluster a estructuras serializables, para el estado y la API."""
    breakdown = cluster.score_breakdown
    return {
        "key": cluster.key,
        "label": cluster.label,
        "intent_type": cluster.intent_type,
        "keywords": cluster.keywords,
        "signal_ids": cluster.signal_ids,
        "subreddits": cluster.subreddits,
        "mention_count": cluster.mention_count,
        "community_count": cluster.community_count,
        "representative_id": cluster.representative_id,
        "job_statement": cluster.job_statement,
        "current_solutions": cluster.current_solutions,
        "risk_flags": cluster.risk_flags,
        "opportunity_score": breakdown.final_score,
        "urgency_tier": breakdown.urgency_tier,
        "score_breakdown": {
            "spread_factor": breakdown.spread_factor,
            "frequency_factor": breakdown.frequency_factor,
            "severity_factor": breakdown.severity_factor,
            "recency_factor": breakdown.recency_factor,
            "paid_signal_factor": breakdown.paid_signal_factor,
            "raw_score": breakdown.raw_score,
            "final_score": breakdown.final_score,
        },
        "evidence": cluster.evidence,
    }
