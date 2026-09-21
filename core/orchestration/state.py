"""
Estado Canónico del Grafo y Puente entre Capas
==============================================

Define lo que viaja por la máquina de estados y la conversión de frontera
entre el modelo analítico de la Fase 3 (`AnalyzedSignal`) y el modelo de
persistencia de la Fase 4 (`OpportunityRecord`).

Sobre los reductores: el grafo es cíclico, así que hay que distinguir entre
las claves que describen *la página que se está procesando* (se reemplazan en
cada vuelta) y las que describen *el resultado acumulado de la ejecución*
(se concatenan). Sin esa distinción, un segundo ciclo o bien perdería lo ya
cosechado o bien reprocesaría la página anterior.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from core.intelligence import AnalyzedSignal
from core.storage import OpportunityRecord

# Dos umbrales para dos preguntas distintas (ver aggregation.py):
#
#   SIGNAL_THRESHOLD              ¿esta queja entra al almacén y al feed?
#   OPPORTUNITY_CLUSTER_THRESHOLD ¿este problema recurrente merece producto?
#
# Aplicar el segundo a mensajes sueltos era la deuda D6: una señal
# individual tiene un techo aritmético de 60 y jamás lo superaba.
SIGNAL_THRESHOLD = 20.0
OPPORTUNITY_CLUSTER_THRESHOLD = 60.0

# Nombre histórico del corte de oportunidad. Se conserva porque eso es lo
# que siempre significó: el umbral de la oportunidad consolidada.
MIN_OPPORTUNITY_SCORE = OPPORTUNITY_CLUSTER_THRESHOLD

# Banderas que vetan una oportunidad con independencia de su puntuación.
BLOCKING_RISK_FLAGS = frozenset({
    "affiliate_or_referral_pattern",
    "affiliate_or_promo_spam",
    "astroturfing",
})


# Contadores que NO se suman entre ciclos.
#
# La agregación recalcula los clusters enteros sobre toda la cosecha en cada
# vuelta, así que su número es un total, no un incremento. Sumarlos daba
# cifras infladas: dos vueltas que ven 2 y luego 3 clusters reportaban 5,
# cuando los clusters que existen son 3.
RECOMPUTED_STATS = frozenset({"clusters", "qualified_clusters"})


def _merge_stats(left: Dict[str, int], right: Dict[str, int]) -> Dict[str, int]:
    """
    Fusiona los contadores de dos vueltas del ciclo.

    Los incrementales se suman (cada ciclo lee posts nuevos); los que se
    recalculan enteros se reemplazan por la última lectura.
    """
    merged = dict(left or {})
    for key, value in (right or {}).items():
        if key in RECOMPUTED_STATS:
            merged[key] = value
        else:
            merged[key] = merged.get(key, 0) + value
    return merged


class RadarState(TypedDict, total=False):
    """Estado canónico que recorre el grafo."""

    # --- Parámetros de la petición (constantes durante la ejecución) ---
    subreddit: str
    limit: int
    sort: str

    # --- Posición en la fuente (se reemplazan en cada ciclo) ---
    cursor: Optional[str]
    cycle: int

    # --- Material en curso (se reemplaza en cada ciclo) ---
    raw_items: List[Dict[str, Any]]
    filtered_items: List[Dict[str, Any]]
    signals: List[AnalyzedSignal]

    # --- Cosecha acumulada de toda la ejecución ---
    stored_ids: Annotated[List[str], operator.add]
    qualified: Annotated[List[Dict[str, Any]], operator.add]
    errors: Annotated[List[str], operator.add]
    stats: Annotated[Dict[str, int], _merge_stats]

    # La agregación necesita TODA la cosecha, no solo la página en curso:
    # un problema que aparece una vez por ciclo solo se ve al juntarlos.
    all_signals: Annotated[List[AnalyzedSignal], operator.add]

    # Se recalculan enteros en cada vuelta sobre `all_signals`, así que se
    # reemplazan en lugar de acumularse.
    clusters: List[Dict[str, Any]]
    qualified_clusters: List[Dict[str, Any]]


def new_state(
    subreddit: str,
    limit: int = 25,
    sort: str = "hot",
) -> RadarState:
    """Construye el estado inicial de una ejecución."""
    return RadarState(
        subreddit=subreddit,
        limit=limit,
        sort=sort,
        cursor=None,
        cycle=0,
        raw_items=[],
        filtered_items=[],
        signals=[],
        stored_ids=[],
        qualified=[],
        errors=[],
        stats={},
        all_signals=[],
        clusters=[],
        qualified_clusters=[],
    )


def signal_to_record(
    signal: AnalyzedSignal,
    raw_score: int = 0,
) -> OpportunityRecord:
    """
    Convierte una señal analizada en un registro persistible.

    Es el puente entre la Fase 3 y la Fase 4. Dos detalles que no son obvios:

    - La puntuación de oportunidad y el nivel de urgencia viven en
      `score_breakdown`, no en la señal; son el resultado del scoring temporal.
    - `AnalyzedSignal` no arrastra los votos de Reddit, que se pierden en el
      análisis, así que el llamante los aporta desde el ítem crudo con
      `raw_score`.

    El vector se deja vacío a propósito: lo genera el almacén con el embedder
    que tenga configurado, que es quien conoce la dimensión correcta.
    """
    return OpportunityRecord(
        id=signal.id,
        text=signal.text,
        subreddit=signal.subreddit,
        author=signal.author,
        score=int(raw_score),
        created_utc=float(signal.created_utc),
        buying_intent=signal.buying_intent,
        pain_severity=signal.pain_severity,
        urgency_tier=signal.score_breakdown.urgency_tier,
        opportunity_score=float(signal.score_breakdown.final_score),
        job_statement=signal.jtbd.job_statement,
        current_solution=signal.jtbd.current_solution,
        workaround_detected=bool(signal.jtbd.workaround_detected),
        url=signal.jtbd.source_url,
        vector=[],
    )
