"""
Juez completo (F3)
==================

calidad (etapa 0) -> etiquetado (1) -> agrupación (2) -> dimensiones y
compuertas (3 y 4) -> abogado del diablo (5). El LLM etiqueta y argumenta;
el veredicto lo decide el código. Devuelve los veredictos listos para
`PostgresStore.save_verdicts` y un resumen con cifras para el informe y la
interfaz.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from core.evidence.model import EvidenceItem
from core.llm.base import LLMProvider
from core.storage.identity import Previo

from .advocate import run_advocate
from .clustering import cluster_evidence
from .gates import judge_cluster
from .labels import LabelCache, VerifiedLabel, label_items
from .quality import filter_quality


@dataclass
class JudgeResult:
    verdicts: list[dict[str, Any]] = field(default_factory=list)
    labels: dict[str, VerifiedLabel] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)


def run_judge(
    items: Sequence[EvidenceItem],
    vectors: Mapping[str, Sequence[float]],
    *,
    provider: LLMProvider | None,
    model: str | None,
    cache: LabelCache,
    now: datetime,
    previous: Sequence[Previo] = (),
) -> JudgeResult:
    calidad = filter_quality(items)
    etiquetas = label_items(calidad.kept, provider=provider, model=model, cache=cache)
    grupos = cluster_evidence(calidad.kept, vectors, previous=previous)
    por_id = {i.id: i for i in calidad.kept}

    veredictos: list[dict[str, Any]] = []
    for grupo in grupos:
        miembros = [por_id[m] for m in grupo.member_ids]
        juicio = judge_cluster(miembros, etiquetas, now=now)
        abogado = run_advocate(juicio, miembros, provider=provider, model=model)
        veredictos.append({
            "opportunity_id": grupo.opportunity_id,
            "cluster_key": grupo.key,
            "keywords": grupo.keywords,
            "verdict": abogado.verdict_after,
            "rule": juicio.rule,
            "score": juicio.score.score,
            "weights_version": juicio.score.weights_version,
            "missing": juicio.missing,
            "gates": [asdict(g) for g in juicio.gates],
            "dimensions": [asdict(d) for d in juicio.score.dimensions],
            "advocate": {
                "verdict_before": abogado.verdict_before,
                "verdict_after": abogado.verdict_after,
                "downgraded": abogado.downgraded,
                "reason": abogado.reason,
                "arguments": [a.model_dump() for a in abogado.arguments],
                "discarded": [a.model_dump() for a in abogado.discarded],
            },
            "member_ids": grupo.member_ids,
            "sources": dict(Counter(m.source for m in miembros)),
        })

    sin_etiqueta = Counter(e.undetermined_reason for e in etiquetas.values() if e.undetermined_reason)
    return JudgeResult(veredictos, etiquetas, {
        "items": len(items),
        "kept": len(calidad.kept),
        "discarded": dict(Counter(v.reason for v in calidad.discarded if v.reason)),
        "competition": len(calidad.competition),
        "labeled": sum(1 for e in etiquetas.values() if e.undetermined_reason is None),
        "undetermined": dict(sin_etiqueta),
        "clusters": len(grupos),
        "verdicts": dict(Counter(v["verdict"] for v in veredictos)),
    })
