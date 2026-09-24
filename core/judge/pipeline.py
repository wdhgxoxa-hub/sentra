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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

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
from .coherencia import comprobar_coherencia, compuerta_coherencia
from .dimensions import es_lanzamiento, pain_items
from .gates import judge_cluster, umbral_autores
from .labels import BATCH_SIZE, LABELER_VERSION, LabelCache, VerifiedLabel, label_items
from .quality import filter_quality


def frase_del_problema(etiqueta: VerifiedLabel) -> str:
    """El fragmento verificado que justifica is_pain: qué problema hay. El de
    affected prueba quién lo sufre y con datos reales solía ser la presentación
    («I'm building an app…»), que juntó a 20 autores distintos (clustering-v6)."""
    return etiqueta.evidence_spans["is_pain"]


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
    vectores_frase: Callable[[Mapping[str, str]], Mapping[str, Sequence[float]]],
    previous: Sequence[Previo] = (),
    label_batch_size: int = BATCH_SIZE,
    tema: Sequence[str] = (),
) -> JudgeResult:
    """`tema`: términos del perfil del escaneo; no nombran nichos.

    `vectores_frase` vectoriza {id: frase del problema verificada}: se agrupa por
    el problema que cada autor cuenta, no por el post entero (clustering-v5/v6).
    `vectors` (texto entero) solo sirve para el contexto de G7."""
    calidad = filter_quality(items)
    etiquetas = label_items(calidad.kept, provider=provider, model=model, cache=cache,
                            batch_size=label_batch_size)
    # AUD2-001: solo la evidencia con dolor pertinente forma nichos. Antes se
    # agrupaba todo lo que pasaba la calidad y los grupos salían por tema.
    dolor = pain_items(calidad.kept, etiquetas)
    ids_dolor = {i.id for i in dolor}
    frases = {i.id: frase_del_problema(etiquetas[i.id]) for i in dolor}
    grupos = cluster_evidence(dolor, vectores_frase(frases), previous=previous, excluir=tema,
                              frases=frases)
    min_autores = umbral_autores(len(dolor))
    sin_dolor = [i for i in calidad.kept if i.id not in ids_dolor and i.id in vectors]
    por_id = {i.id: i for i in calidad.kept}

    # G0 (residuos de AUD2-001 y 006): una sola llamada con las frases de todos los grupos.
    coherencias = comprobar_coherencia({g.key: [frases[m] for m in g.member_ids] for g in grupos},
                                       provider=provider, model=model)

    veredictos: list[dict[str, Any]] = []
    for grupo in grupos:
        miembros = [por_id[m] for m in grupo.member_ids]
        # Lo que no es dolor pero está tan cerca como para caber en el grupo
        # informa a G7 (quién habla bien de un competidor gratuito). Se compara en
        # el espacio del texto entero: el de las frases no sirve para piezas sin dolor.
        textos = [_unitario(vectors[m]) for m in grupo.member_ids if m in vectors]
        centro = _unitario(np.mean(textos, axis=0)) if textos else None
        contexto = [] if centro is None else [
            i for i in sin_dolor if float(_unitario(vectors[i.id]) @ centro) >= CLUSTER_MIN_SIMILARITY]
        juicio = judge_cluster(miembros, etiquetas, now=now, min_authors=min_autores, contexto=contexto,
                               coherencia=compuerta_coherencia(coherencias[grupo.key]))
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
        "incoherent": sum(1 for c in coherencias.values() if c.estado == "distinto"),
        "coherence_unchecked": sum(1 for c in coherencias.values() if c.estado == "sin_comprobar"),
        "verdicts": dict(Counter(v["verdict"] for v in veredictos)),
    })
