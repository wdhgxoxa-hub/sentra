"""
Módulo de Ponderación y Decaimiento Temporal Exponencial (Opportunity Radar)
==========================================================================
Extraído y adaptado de painpoint-atlas (opportunity_radar/scoring.py).

Proporciona:
1. Función matemática de decaimiento temporal exponencial: recency = exp(-dias / 180).
2. Ponderación multi-eje para priorización de oportunidades comerciales:
   - Dispersión comunitaria (Spread: 25%)
   - Frecuencia media de recurrencia (Frequency: 25%)
   - Severidad del dolor (Severity: 20%)
   - Frescura temporal (Recency: 15%)
   - Señal de disposición a pagar (Paid Signal: 15%)
3. Calibración continua para evitar sesgos por quejas antiguas o usuarios ruidosos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import exp
from typing import Any, Dict, List, Optional, Sequence
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class OpportunityMetrics:
    """Métricas numéricas agregadas de un clúster de dolor u oportunidad."""
    mention_count: int
    community_count: int
    average_mentions_per_community: float
    average_severity: float       # Escala 1.0 (leve) a 5.0 (crítico/bloqueante)
    average_paid_signal: float   # Escala 0.0 (ninguna) a 3.0 (disposición explícita)
    newest_age_days: float        # Días transcurridos desde la mención más reciente


class TemporalScoreBreakdown(BaseModel):
    """Desglose de factores ponderados del puntaje de oportunidad."""
    spread_factor: float          # 0.0 - 1.0
    frequency_factor: float       # 0.0 - 1.0
    severity_factor: float        # 0.0 - 1.0
    recency_factor: float         # 0.0 - 1.0
    paid_signal_factor: float     # 0.0 - 1.0
    raw_score: float              # 0.0 - 100.0
    final_score: float            # 0.0 - 100.0 (redondeado)
    urgency_tier: str             # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"


class TemporalScorer:
    """
    Motor matemático de priorización de oportunidades comerciales y decaimiento temporal.
    """

    DEFAULT_WEIGHTS = {
        "spread": 0.25,
        "frequency": 0.25,
        "severity": 0.20,
        "recency": 0.15,
        "paid_signal": 0.15,
    }

    def __init__(
        self,
        half_life_days: float = 180.0,
        weights: Optional[Dict[str, float]] = None,
    ) -> None:
        self.half_life_days = half_life_days
        self.weights = weights or self.DEFAULT_WEIGHTS

        # Normalizar pesos para asegurar suma = 1.0
        total_w = sum(self.weights.values())
        if total_w > 0:
            self.weights = {k: v / total_w for k, v in self.weights.items()}

    def calculate_recency(self, newest_age_days: float) -> float:
        """
        Calcula la curva de decaimiento exponencial según los días de antigüedad.
        recency = exp(-max(dias, 0) / half_life_days).
        - 0 días -> 1.0 (frescura máxima)
        - 90 días -> ~0.60
        - 180 días -> ~0.37
        - 365 días -> ~0.13
        """
        safe_days = max(float(newest_age_days), 0.0)
        return float(exp(-safe_days / self.half_life_days))

    def calculate_spread(self, community_count: int, benchmark_target: int = 5) -> float:
        """Mide si el dolor afecta a múltiples comunidades independientes (evita sesgo local)."""
        return min(max(community_count / float(benchmark_target), 0.0), 1.0)

    def calculate_frequency(self, avg_mentions: float, benchmark_target: float = 5.0) -> float:
        """Mide la recurrencia media del problema por comunidad."""
        return min(max(avg_mentions / benchmark_target, 0.0), 1.0)

    def calculate_severity(self, avg_severity_1_to_5: float) -> float:
        """Normaliza la severidad cualitativa (1.0 a 5.0) a una escala 0.0 - 1.0."""
        return min(max((float(avg_severity_1_to_5) - 1.0) / 4.0, 0.0), 1.0)

    def calculate_paid_signal(self, avg_paid_signal_0_to_3: float) -> float:
        """Normaliza la señal de disposición a pagar (0.0 a 3.0) a escala 0.0 - 1.0."""
        return min(max(float(avg_paid_signal_0_to_3) / 3.0, 0.0), 1.0)

    def score(self, metrics: OpportunityMetrics) -> TemporalScoreBreakdown:
        """
        Ejecuta la fórmula completa de ponderación y retorna el desglose detallado.
        """
        spread = self.calculate_spread(metrics.community_count)
        freq = self.calculate_frequency(metrics.average_mentions_per_community)
        sev = self.calculate_severity(metrics.average_severity)
        rec = self.calculate_recency(metrics.newest_age_days)
        paid = self.calculate_paid_signal(metrics.average_paid_signal)

        raw = 100.0 * (
            self.weights["spread"] * spread
            + self.weights["frequency"] * freq
            + self.weights["severity"] * sev
            + self.weights["recency"] * rec
            + self.weights["paid_signal"] * paid
        )
        final = round(raw, 2)

        if final >= 80.0:
            urgency = "CRITICAL"
        elif final >= 60.0:
            urgency = "HIGH"
        elif final >= 40.0:
            urgency = "MEDIUM"
        else:
            urgency = "LOW"

        return TemporalScoreBreakdown(
            spread_factor=round(spread, 4),
            frequency_factor=round(freq, 4),
            severity_factor=round(sev, 4),
            recency_factor=round(rec, 4),
            paid_signal_factor=round(paid, 4),
            raw_score=round(raw, 4),
            final_score=final,
            urgency_tier=urgency
        )

    @staticmethod
    def calculate_age_days(created_utc: float, reference_time: Optional[datetime] = None) -> float:
        """Calcula los días transcurridos desde una marca de tiempo UTC."""
        ref = reference_time or datetime.now(timezone.utc)
        created_dt = datetime.fromtimestamp(created_utc, tz=timezone.utc)
        elapsed_seconds = (ref - created_dt).total_seconds()
        return max(0.0, elapsed_seconds / 86400.0)
