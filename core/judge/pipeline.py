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

from core.evidence.model import EvidenceItem, SearchQuery
from core.llm.base import JsonGenerator
from core.sources.profile import menciona_el_tema
from core.storage.identity import Previo

from .advocate import run_advocate
from .clustering import (
    CLUSTER_MIN_SIMILARITY,
    CLUSTERING_VERSION,
    _unitario,
    cluster_evidence,
    subgrupo,
)
from .coherencia import CoherenceCache, comprobar_coherencia, compuerta_coherencia
from .dimensions import es_anuncio, es_lanzamiento, pain_items
from .gates import judge_cluster, umbral_autores
from .labels import (
    BATCH_SIZE,
    MAX_ITEMS_PER_SCAN,
    LabelCache,
    TemaDelEscaneo,
    VerifiedLabel,
    etiquetador,
    label_items,
)
from .quality import QualityResult, QualityVerdict, filter_quality


def contexto_de_g7(grupos: Mapping[str, Sequence[str]], sin_dolor: Sequence[EvidenceItem],
                   vectors: Mapping[str, Sequence[float]]) -> dict[str, list[EvidenceItem]]:
    """Lo que no es dolor pero está tan cerca como para caber en el grupo informa a
    G7 (quién habla bien de un competidor gratuito). Se compara en el espacio del
    texto entero: el de las frases no sirve para piezas sin dolor.

    Cada pieza va al contexto de un solo grupo, el de centro más cercano, y solo si
    lo supera CLUSTER_MIN_SIMILARITY: en un escaneo de un solo tema casi todas
    superaban el umbral con todos los grupos y G7 era el mismo para todos."""
    centros: dict[str, np.ndarray] = {}
    for clave, ids in grupos.items():
        textos = [_unitario(vectors[m]) for m in ids if m in vectors]
        if textos:
            centros[clave] = _unitario(np.mean(textos, axis=0))
    contextos: dict[str, list[EvidenceItem]] = {clave: [] for clave in grupos}
    for item in sin_dolor:
        if item.id not in vectors or not centros:
            continue
        vector = _unitario(vectors[item.id])
        similitud, clave = max((float(vector @ centro), clave) for clave, centro in centros.items())
        if similitud >= CLUSTER_MIN_SIMILARITY:
            contextos[clave].append(item)
    return contextos


def sin_comentarios_fuera_de_tema(calidad: QualityResult, tema: Sequence[str]) -> QualityResult:
    """Con tema, un comentario cuyo texto propio no lo nombra no se etiqueta
    («off_topic»). En el escaneo de impagos, la mitad del «dolor» eran
    comentarios de YouTube sobre el propio vídeo y mezclaban los grupos. Los
    posts no cambian: su título ya es parte de su texto."""
    if not tema:
        return calidad
    consulta = SearchQuery(keywords=list(tema))
    fuera = {i.id for i in calidad.kept if i.kind == "comment" and not menciona_el_tema(i.text, consulta)}
    if not fuera:
        return calidad
    return QualityResult(
        kept=[i for i in calidad.kept if i.id not in fuera],
        discarded=[*calidad.discarded, *(QualityVerdict(i, False, "off_topic", False) for i in sorted(fuera))],
        competition=[v for v in calidad.competition if v.item_id not in fuera])


def orden_de_etiquetado(items: Sequence[EvidenceItem], tema: Sequence[str]) -> list[EvidenceItem]:
    """En qué orden se etiqueta: con el tope de etiquetado, el orden decide qué
    entra. Primero lo que nombra el tema y, dentro de cada parte, por turnos
    entre fuentes. En orden de llegada, la fuente más ruidosa (cientos de
    comentarios de YouTube o posts de Bluesky) se llevaba todo el cupo."""
    if not tema:  # descubrimiento: sin tema que mirar, quedan solo los turnos
        return _por_turnos(items)
    consulta = SearchQuery(keywords=list(tema))
    del_tema = [i for i in items if menciona_el_tema(f"{i.title or ''} {i.text}", consulta)]
    ids = {i.id for i in del_tema}
    return _por_turnos(del_tema) + _por_turnos([i for i in items if i.id not in ids])


def _por_turnos(items: Sequence[EvidenceItem]) -> list[EvidenceItem]:
    colas: dict[str, list[EvidenceItem]] = {}
    for item in items:
        colas.setdefault(item.source, []).append(item)
    salida: list[EvidenceItem] = []
    while any(colas.values()):
        for cola in colas.values():
            if cola:
                salida.append(cola.pop(0))
    return salida


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
    label_max_items: int = MAX_ITEMS_PER_SCAN,
    tema: Sequence[str] = (),
    coherence_cache: CoherenceCache | None = None,
    descripcion: str = "",
) -> JudgeResult:
    """`tema`: términos del perfil del escaneo; no nombran nichos.

    `vectores_frase` vectoriza {id: frase del problema verificada}: se agrupa por
    el problema que cada autor cuenta, no por el post entero (clustering-v5/v6).
    `vectors` (texto entero) solo sirve para el contexto de G7.

    `descripcion`: el tema como lo escribió la persona. Con tema, el etiquetador
    lo conoce (labels-v5) y solo las quejas del tema forman grupos."""
    calidad = sin_comentarios_fuera_de_tema(filter_quality(items), tema)
    tema_etiquetado = (TemaDelEscaneo(descripcion=descripcion or ", ".join(tema), palabras=tuple(tema))
                       if tema else None)
    etiquetas = label_items(orden_de_etiquetado(calidad.kept, tema), provider=provider, model=model, cache=cache,
                            batch_size=label_batch_size, max_items=label_max_items, tema=tema_etiquetado)
    # AUD2-001: solo la evidencia con dolor pertinente forma nichos. Antes se
    # agrupaba todo lo que pasaba la calidad y los grupos salían por tema.
    dolor = pain_items(calidad.kept, etiquetas)
    ids_dolor = {i.id for i in dolor}
    frases = {i.id: frase_del_problema(etiquetas[i.id]) for i in dolor}
    vectores_de_frase = vectores_frase(frases)
    grupos = cluster_evidence(dolor, vectores_de_frase, previous=previous, excluir=tema, frases=frases)
    min_autores = umbral_autores(len(dolor))
    sin_dolor = [i for i in calidad.kept if i.id not in ids_dolor and i.id in vectors]
    por_id = {i.id: i for i in calidad.kept}

    # G0 (residuos de AUD2-001 y 006): una sola llamada con las frases de todos los grupos.
    coherencias = comprobar_coherencia({g.key: {m: frases[m] for m in g.member_ids} for g in grupos},
                                       provider=provider, model=model, cache=coherence_cache)
    # G0 v2: una mezcla con un problema dominante se separa (el resto vuelve a ser
    # piezas sueltas) y el subgrupo se comprueba otra vez, todos en una llamada.
    separados = {g.key: subgrupo(g, coherencias[g.key].dominantes, vectores_de_frase, frases=frases,
                                 fondo=list(frases.values()), previous=previous, excluir=tema)
                 for g in grupos if coherencias[g.key].dominantes}
    if separados:
        coherencias.update(comprobar_coherencia(
            {s.key: {m: frases[m] for m in s.member_ids} for s in separados.values()},
            provider=provider, model=model, cache=coherence_cache))
        grupos = [separados.get(g.key, g) for g in grupos]

    contextos = contexto_de_g7({g.key: g.member_ids for g in grupos}, sin_dolor, vectors)
    veredictos: list[dict[str, Any]] = []
    for grupo in grupos:
        miembros = [por_id[m] for m in grupo.member_ids]
        juicio = judge_cluster(miembros, etiquetas, now=now, min_authors=min_autores,
                               contexto=contextos[grupo.key],
                               coherencia=compuerta_coherencia(coherencias[grupo.key]))
        abogado = run_advocate(juicio, miembros, provider=provider, model=model)
        veredictos.append({
            "opportunity_id": grupo.opportunity_id,
            "cluster_key": grupo.key,
            "keywords": grupo.keywords,
            # El nombre que da G0 a un mismo problema (es/en): lo comparten Radar y dossier.
            "problem_name": coherencias[grupo.key].nombre,
            "verdict": abogado.verdict_after,
            "rule": juicio.rule,
            # Una mezcla (G0 fallida) no tiene problema común que puntuar (decisión del usuario).
            "score": None if juicio.rule.startswith("0:") else juicio.score.score,
            "weights_version": juicio.score.weights_version,
            "labeler_version": etiquetador(model, tema_etiquetado),
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
        # labels-v5: quejas que no son del tema del escaneo (no forman grupos).
        "pain_off_topic": sum(1 for i in calidad.kept if (e := etiquetas.get(i.id)) is not None
                             and e.is_pain == "yes" and e.del_tema in ("no", "undetermined")
                             and not es_anuncio(i)),
        "launches_excluded": sum(1 for i in calidad.kept if es_lanzamiento(i)),
        "min_authors": min_autores,
        "clusters": len(grupos),
        "split": len(separados),
        "incoherent": sum(1 for g in grupos if coherencias[g.key].estado == "distinto"),
        "coherence_unchecked": sum(1 for g in grupos if coherencias[g.key].estado == "sin_comprobar"),
        "verdicts": dict(Counter(v["verdict"] for v in veredictos)),
    })
