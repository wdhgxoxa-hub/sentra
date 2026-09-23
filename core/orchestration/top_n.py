"""
Las 6 mejores oportunidades (AUD-007)
=====================================

Un escaneo tiene un objetivo explícito: entregar las TOP_N oportunidades
cualificadas de mayor puntuación, o decir honestamente por qué no hay TOP_N.
Nunca se rellena con problemas que no superan el corte.

Criterio de parada (compartido por el grafo y por el resultado, para que no
puedan discrepar):

    fallo de acceso a la fuente        -> sin_acceso_reddit
    >= TOP_N problemas cualificados    -> completo
    cursor nulo (la fuente se agotó)   -> datos_insuficientes o fuentes_agotadas
    límite de ciclos alcanzado         -> limite_ciclos

`datos_insuficientes` y `fuentes_agotadas` se distinguen por lo que había:
si ni siquiera existen TOP_N problemas (cualificados o no), faltan datos; si
existen pero no alcanzan el corte, la fuente se agotó sin dar la talla.

Ranking, determinista y documentado en `rank_key`:
    1. final_score, de mayor a menor;
    2. menciones, de más a menos;
    3. comunidades, de más a menos;
    4. clave del problema, alfabética (desempate final, siempre único).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

#: Cuántas oportunidades se entregan. Único origen: la interfaz lo recibe del
#: backend (columna `pipeline_runs.top_n_target`), no lo repite.
TOP_N = 6

IncompleteReason = Literal[
    "fuentes_agotadas",
    "limite_ciclos",
    "sin_acceso_reddit",
    "datos_insuficientes",
]

StopReason = Literal["failure", "complete", "exhausted", "cycles"]


def rank_key(cluster: Mapping[str, Any]) -> tuple[float, int, int, str]:
    """Clave de orden del ranking (ver cabecera)."""
    return (
        -float(cluster.get("opportunity_score", 0.0)),
        -int(cluster.get("mention_count", 0)),
        -int(cluster.get("community_count", 0)),
        str(cluster.get("key", "")),
    )


def rank_top(clusters: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Las TOP_N primeras según `rank_key`. Recibe solo cualificadas."""
    return [dict(c) for c in sorted(clusters, key=rank_key)[:TOP_N]]


def stop_reason(state: Mapping[str, Any], max_cycles: int) -> StopReason | None:
    """Por qué debe terminar la ejecución, o None si hay que seguir."""
    if state.get("failure"):
        return "failure"
    if len(state.get("qualified_clusters") or []) >= TOP_N:
        return "complete"
    if state.get("cursor") is None:
        return "exhausted"
    if int(state.get("cycle", 0)) >= max_cycles:
        return "cycles"
    return None


def run_outcome(
    qualified: Sequence[Mapping[str, Any]],
    total_clusters: int,
    reason: StopReason | None,
) -> dict[str, Any]:
    """
    Resultado explícito de la ejecución: `{target, found, complete, reason}`.

    `reason` es el motivo tipado de un resultado incompleto, o None si se
    alcanzó TOP_N.
    """
    found = min(len(qualified), TOP_N)
    complete = found >= TOP_N
    motivo: IncompleteReason | None = None
    if not complete:
        if reason == "failure":
            motivo = "sin_acceso_reddit"
        elif reason == "cycles":
            motivo = "limite_ciclos"
        elif total_clusters < TOP_N:
            motivo = "datos_insuficientes"
        else:
            motivo = "fuentes_agotadas"
    return {"target": TOP_N, "found": found, "complete": complete, "reason": motivo}
