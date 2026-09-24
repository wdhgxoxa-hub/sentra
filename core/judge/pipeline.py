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
from core.llm.base import JsonGenerator
from core.storage.identity import Previo

from .advocate import run_advocate
from .clustering import (
    CLUSTER_MIN_SIMILARITY,
    CLUSTERING_VERSION,
    _unitario,
    cluster_evidence,
)
from .dimensions import es_lanzamiento, pain_items
from .gates import judge_cluster, umbral_autores
from .labels import BATCH_SIZE, LABELER_VERSION, LabelCache, VerifiedLabel, label_items
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
    provider: JsonGenerator | None,
    model: str | None,
    cache: LabelCache,
    now: datetime,
    previous: Sequence[Previo] = (),
    label_batch_size: int = BATCH_SIZE,
    tema: Sequence[str] = (),
) -> JudgeResult:
    """`tema`: términos del perfil del escaneo; no nombran nichos."""
    calidad = filter_quality(items)
    etiquetas = label_items(calidad.kept, provider=provider, model=model, cache=cache,
                            batch_size=label_batch_size)
    # AUD2-001: solo la evidencia con dolor pertinente forma nichos. Antes se
    # agrupaba todo lo que pasaba la calidad y los grupos salían por tema.
    dolor = pain_items(calidad.kept, etiquetas)
    ids_dolor = {i.id for i in dolor}
    grupos = cluster_evidence(dolor, vectors, previous=previous, excluir=tema)
    min_autores = umbral_autores(len(dolor))
    sin_dolor = [i for i in calidad.kept if i.id not in ids_dolor and i.id in vectors]
    por_id = {i.id: i for i in calidad.kept}

    veredictos: list[dict[str, Any]] = []
    for grupo in grupos:
        miembros = [por_id[m] for m in grupo.member_ids]
        # Lo que no es dolor pero está tan cerca como para caber en el grupo
        # informa a G7 (quién habla bien de un competidor gratuito).
        centro = _unitario(grupo.centroid)
        contexto = [i for i in sin_dolor
                    if float(_unitario(vectors[i.id]) @ centro) >= CLUSTER_MIN_SIMILARITY]
        juicio = judge_cluster(miembros, etiquetas, now=now, min_authors=min_autores, contexto=contexto)
        abogado = run_advocate(juicio, miembros, provider=provider, model=model)
        veredictos.append({
            "opportunity_id": grupo.opportunity_id,
            "cluster_key": grupo.key,
            "keywords": grupo.keywords,
            "verdict": abogado.verdict_after,
            "rule": juicio.rule,
            "score": juicio.score.score,
            "weights_version": juicio.score.weights_version,
            "labeler_version": f"{LABELER_VERSION}/{model}" if model else LABELER_VERSION,
            "clustering_version": CLUSTERING_VERSION,
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
        "pain": len(dolor),
        "launches_excluded": sum(1 for i in calidad.kept if es_lanzamiento(i)),
        "min_authors": min_autores,
        "clusters": len(grupos),
        "verdicts": dict(Counter(v["verdict"] for v in veredictos)),
    })
