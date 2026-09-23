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
from typing import Annotated, Any, TypedDict

from core.intelligence import AnalyzedSignal
from core.storage import OpportunityRecord

# Dos umbrales para dos preguntas distintas. Este es su ÚNICO origen.
#
#   MIN_SIGNAL_SCORE       ¿esta queja suelta entra al feed como cualificada?
#   MIN_OPPORTUNITY_SCORE  ¿este problema consolidado merece producto?
#
# La aritmética (pesos de TemporalScorer, ver aggregation.py): una señal
# suelta tiene `spread` y `frequency` clavados en 1/5, que aportan 10 puntos
# fijos; la recencia da hasta 15, la severidad hasta 20 y la disposición a
# pagar hasta 15. Su techo es exactamente 60.
#
# - MIN_SIGNAL_SCORE = 20 es alcanzable por una señal: una queja de los
#   últimos ~72 días (10 + 15·e^(-d/180) >= 20) pasa aunque su severidad sea
#   indeterminada y no mencione dinero; una más vieja necesita severidad o
#   disposición a pagar.
# - MIN_OPPORTUNITY_SCORE = 60 es el techo de una señal: solo lo superan
#   problemas con difusión o recurrencia reales, es decir, clusters.
#
# Aplicar el segundo a mensajes sueltos vaciaba el radar (D6, AUD-018).
MIN_SIGNAL_SCORE = 20.0
MIN_OPPORTUNITY_SCORE = 60.0

# Nombres históricos, alias de los anteriores (no son otro origen).
SIGNAL_THRESHOLD = MIN_SIGNAL_SCORE
OPPORTUNITY_CLUSTER_THRESHOLD = MIN_OPPORTUNITY_SCORE

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


def _id_de(elemento: Any) -> str:
    """Id de Reddit de un ítem crudo (dict) o de una señal analizada."""
    if isinstance(elemento, dict):
        return str(elemento.get("id", ""))
    return str(elemento.id)


def _merge_by_id(left: list[Any], right: list[Any]) -> list[Any]:
    """
    Acumula la cosecha de todos los ciclos, una entrada por id de Reddit.

    Un post que vuelve a aparecer en otra página (o en otra vuelta) no es una
    segunda voz: se queda la lectura más reciente, en la posición de la
    primera. Sin esto, repetirlo inflaba menciones y clusters.
    """
    acumulado: dict[str, Any] = {}
    for elemento in [*(left or []), *(right or [])]:
        acumulado[_id_de(elemento)] = elemento
    return list(acumulado.values())


def _merge_stats(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
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
    cursor: str | None
    cycle: int

    # --- Material en curso (se reemplaza en cada ciclo) ---
    raw_items: list[dict[str, Any]]
    filtered_items: list[dict[str, Any]]
    signals: list[AnalyzedSignal]

    # --- Cosecha acumulada de toda la ejecución ---
    stored_ids: Annotated[list[str], operator.add]
    qualified: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]
    stats: Annotated[dict[str, int], _merge_stats]

    # La agregación necesita TODA la cosecha, no solo la página en curso:
    # un problema que aparece una vez por ciclo solo se ve al juntarlos.
    all_signals: Annotated[list[AnalyzedSignal], _merge_by_id]
    # Ítems que pasaron el filtro en TODOS los ciclos: es lo que se persiste
    # como raw_posts (AUD-006). `filtered_items` es solo la página en curso.
    all_items: Annotated[list[dict[str, Any]], _merge_by_id]

    # Se recalculan enteros en cada vuelta sobre `all_signals`, así que se
    # reemplazan en lugar de acumularse.
    clusters: list[dict[str, Any]]
    qualified_clusters: list[dict[str, Any]]

    # Motivo tipado por el que la fuente no entregó datos (AUD-003):
    # `{"code", "message", "retryAfterSeconds"}`. Si existe, la ejecución ha
    # FALLADO: no es una cosecha vacía.
    failure: dict[str, Any] | None

    # Resultado explícito de la ejecución (AUD-007):
    # `{"target", "found", "complete", "reason"}`, ver top_n.run_outcome.
    top: dict[str, Any] | None


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
        all_items=[],
        clusters=[],
        qualified_clusters=[],
        failure=None,
        top=None,
    )


def signal_to_record(
    signal: AnalyzedSignal,
    raw_score: int = 0,
    data_source: str | None = None,
) -> OpportunityRecord:
    """
    Convierte una señal analizada en un registro persistible.

    Es el puente entre la Fase 3 y la Fase 4. Dos detalles que no son obvios:

    - La puntuación de oportunidad y el nivel de urgencia viven en
      `score_breakdown`, no en la señal; son el resultado del scoring temporal.
    - `AnalyzedSignal` no arrastra los votos de Reddit, que se pierden en el
      análisis, así que el llamante los aporta desde el ítem crudo con
      `raw_score`.

    `data_source` ("demo" o "reddit") viaja con cada fila (D-J): la búsqueda
    lee LanceDB sin pasar por la ejecución y tiene que poder decirlo.

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
        data_source=data_source,
        vector=[],
    )
