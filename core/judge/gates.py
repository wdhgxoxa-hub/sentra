"""
Juez, etapa 4: compuertas G1–G8 y veredicto (D-M3)
==================================================

Para CONSTRUIR deben pasar TODAS; cada una se guarda con pasa/falla, valor
medido, umbral e ids de la evidencia que la sostienen.

  G1 Al menos MIN_DISTINCT_SOURCES fuentes distintas (entre los dolores).
  G2 Al menos MIN_DISTINCT_AUTHORS autores distintos (author_hash).
  G3 Al menos 1 parche casero verificado.
  G4 Al menos 1 señal de pago o de búsqueda de herramienta verificada.
  G5 Concentración: ningún hilo ni autor aporta más de CONCENTRATION_MAX_SHARE.
  G6 Recencia: al menos RECENCY_MIN_SHARE de la evidencia en RECENCY_DAYS días.
  G7 Saturación: ningún competidor gratuito mencionado mayoritariamente como
     solución satisfactoria. Un competidor cuenta si lo nombran al menos
     MIN_AUTORES_COMPETIDOR autores distintos; con menos y alguna mención
     favorable, G7 queda «sin datos suficientes» (regla 9).
  G8 Solo datos reales: todos los miembros con data_source 'real' (demo y
     legacy sin procedencia no cuentan, D-M5).

Tabla de veredictos D-M3, en este orden:
  1. Falla G7 -> DESCARTAR.
  2. G2 por debajo de la mitad de N -> DESCARTAR.
  3. Fallan G1 y G2 a la vez -> DESCARTAR.
  4. Falla G8 -> como máximo INVESTIGAR MÁS.
  5. Fallan G1, G2 (con al menos N/2) o G5 -> INVESTIGAR MÁS.
  6. Fallan G3, G4 o G6 -> INVESTIGAR MÁS, diciendo qué falta.
  7. Pasan todas -> CONSTRUIR.
  8. G0 sin comprobar -> como máximo INVESTIGAR MÁS.
  9. G7 con menciones favorables de menos de MIN_AUTORES_COMPETIDOR autores ->
     como máximo INVESTIGAR MÁS (señal sin resolver).
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from core.evidence.model import EvidenceItem

from .dimensions import (
    NicheScore,
    pain_items,
    payment_items,
    score_cluster,
    workaround_items,
)
from .labels import VerifiedLabel

MIN_DISTINCT_SOURCES = 2
MIN_DISTINCT_AUTHORS = 8
MIN_WORKAROUNDS = 1
MIN_PAYMENT_SIGNALS = 1
CONCENTRATION_MAX_SHARE = 0.40
RECENCY_DAYS = 180
RECENCY_MIN_SHARE = 0.50
#: Autores distintos que tienen que nombrar a un competidor para que cuente en G7
#: (aprobado tras E8: un solo lanzamiento de HN descartaba el grupo de impagos).
#: Es el mínimo con el que el juez llama patrón a algo (MIN_CLUSTER_SIZE).
MIN_AUTORES_COMPETIDOR = 3

Verdict = Literal["CONSTRUIR", "INVESTIGAR MÁS", "DESCARTAR"]
#: Orden de los veredictos, del mejor al peor.
VERDICT_RANK: dict[str, int] = {"CONSTRUIR": 0, "INVESTIGAR MÁS": 1, "DESCARTAR": 2}


@dataclass(frozen=True)
class GateResult:
    gate: str
    passed: bool
    value: float
    threshold: float
    evidence_ids: list[str]
    #: False si no había nada que medir (AUD2-005): pasa para decidir, pero no
    #: se enseña como verificada. Solo G7 puede aprobar por ausencia.
    measured: bool = True
    #: Por qué, cuando lo dice un revisor (G0: la razón de la coherencia).
    note: str | None = None


@dataclass(frozen=True)
class ClusterJudgement:
    verdict: Verdict
    #: Compuertas que fallan, en orden.
    missing: list[str]
    #: Regla de la tabla D-M3 que decidió.
    rule: str
    gates: list[GateResult]
    score: NicheScore


def _ids(items: Sequence[EvidenceItem]) -> list[str]:
    return sorted(i.id for i in items)


def _concentracion(dolores: Sequence[EvidenceItem]) -> GateResult:
    if not dolores:
        return GateResult("G5", False, 1.0, CONCENTRATION_MAX_SHARE, [])
    # Un hilo o autor desconocido (None) no es «el mismo» para todos: no concentra.
    hilos = Counter(i.thread_id for i in dolores if i.thread_id)
    autores = Counter(i.author_hash for i in dolores if i.author_hash)
    conteos = list(hilos.items()) + list(autores.items())
    if not conteos:
        return GateResult("G5", True, 0.0, CONCENTRATION_MAX_SHARE, [])
    clave, maximo = max(conteos, key=lambda kv: kv[1])
    cuota = maximo / len(dolores)
    culpables = [i for i in dolores if clave in (i.thread_id, i.author_hash)]
    return GateResult("G5", cuota <= CONCENTRATION_MAX_SHARE, cuota, CONCENTRATION_MAX_SHARE,
                      _ids(culpables))


def _saturacion(items: Sequence[EvidenceItem], labels: Mapping[str, VerifiedLabel]) -> GateResult:
    menciones: dict[str, list[tuple[str, str, bool | None, str]]] = defaultdict(list)
    nombres: dict[str, str] = {}
    for item in items:
        etiqueta = labels.get(item.id)
        for c in etiqueta.competitors if etiqueta else []:
            nombres.setdefault(c.name.casefold(), c.name)
            menciones[c.name.casefold()].append((item.id, c.stance, c.free, item.author_hash or item.id))
    peores: list[str] = []
    cuota_max = 0.0
    medida = False
    pocos: list[tuple[str, int, list[str]]] = []
    for clave, lista in menciones.items():
        if not any(m[2] for m in lista):
            continue
        satisfechos = [m for m in lista if m[1] == "satisfecho"]
        autores = len({m[3] for m in lista})
        if autores < MIN_AUTORES_COMPETIDOR:
            if satisfechos:
                pocos.append((nombres[clave], autores, sorted({m[0] for m in satisfechos})))
            continue
        medida = True
        cuota = len(satisfechos) / len(lista)
        if cuota > cuota_max:
            cuota_max, peores = cuota, sorted({m[0] for m in satisfechos})
    if not medida and pocos:
        nota = "; ".join(f"{nombre}: {n} de {MIN_AUTORES_COMPETIDOR} autores" for nombre, n, _ in pocos)
        return GateResult("G7", True, 0.0, 0.5, sorted({i for *_, ids in pocos for i in ids}),
                          measured=False, note=f"menciones favorables insuficientes ({nota})")
    return GateResult("G7", cuota_max <= 0.5, cuota_max, 0.5, peores, measured=medida)


def normalizar_compuertas(guardadas: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Compuertas leídas de la base con `measured`. Los veredictos anteriores a
    AUD2-005 no lo traen: G7 aprobada sin valor ni evidencia es que nadie
    mencionó un competidor gratuito, es decir, que no se midió."""
    salida = []
    for g in guardadas:
        copia = dict(g)
        if "measured" not in copia:
            copia["measured"] = not (copia.get("gate") == "G7" and copia.get("passed")
                                     and not copia.get("evidence_ids") and not copia.get("value"))
        copia.setdefault("note", None)  # antes de G0 ninguna compuerta llevaba nota
        salida.append(copia)
    return salida


#: G2 relativo al escaneo (AUD2-001, DP2 A): 8 autores fijos no se alcanzaban con
#: ~100 piezas. N = 10 % del dolor pertinente del escaneo, entre 3 y 8.
G2_MIN_ABSOLUTO = 3
G2_FRACCION = 0.10


def umbral_autores(dolor_del_escaneo: int) -> int:
    """Autores distintos que exige G2 para un escaneo con tanto dolor pertinente."""
    return min(MIN_DISTINCT_AUTHORS, max(G2_MIN_ABSOLUTO, math.ceil(G2_FRACCION * dolor_del_escaneo)))


def evaluate_gates(items: Sequence[EvidenceItem], labels: Mapping[str, VerifiedLabel], *,
                   now: datetime, min_authors: int = MIN_DISTINCT_AUTHORS,
                   contexto: Sequence[EvidenceItem] = ()) -> list[GateResult]:
    """`contexto`: evidencia sin dolor cercana al grupo; solo cuenta para G7
    (quién habla bien de un competidor gratuito)."""
    dolores = pain_items(items, labels)
    fuentes = {i.source for i in dolores}
    autores = {i.author_hash for i in dolores if i.author_hash}
    pago, parches = payment_items(items, labels), workaround_items(items, labels)
    recientes = [i for i in dolores if i.created_at >= now - timedelta(days=RECENCY_DAYS)]
    cuota_reciente = len(recientes) / len(dolores) if dolores else 0.0
    no_reales = [i for i in items if i.data_source != "real"]
    return [
        GateResult("G1", len(fuentes) >= MIN_DISTINCT_SOURCES, len(fuentes), MIN_DISTINCT_SOURCES,
                   _ids(dolores)),
        GateResult("G2", len(autores) >= min_authors, len(autores), min_authors, _ids(dolores)),
        GateResult("G3", len(parches) >= MIN_WORKAROUNDS, len(parches), MIN_WORKAROUNDS, _ids(parches)),
        GateResult("G4", len(pago) >= MIN_PAYMENT_SIGNALS, len(pago), MIN_PAYMENT_SIGNALS, _ids(pago)),
        _concentracion(dolores),
        GateResult("G6", bool(dolores) and cuota_reciente >= RECENCY_MIN_SHARE, cuota_reciente,
                   RECENCY_MIN_SHARE, _ids(recientes)),
        _saturacion([*items, *contexto], labels),
        GateResult("G8", not no_reales, len(no_reales), 0, _ids(no_reales)),
    ]


def decide(gates: Sequence[GateResult], *, min_authors: int = MIN_DISTINCT_AUTHORS) -> tuple[Verdict, str]:
    """Tabla D-M3. Devuelve (veredicto, regla que decidió)."""
    por = {g.gate: g for g in gates}
    falla = {g.gate for g in gates if not g.passed}
    coherencia = por.get("G0")
    if coherencia is not None and coherencia.measured and not coherencia.passed:
        return "DESCARTAR", "0: no es un mismo problema (G0)"
    if "G7" in falla:
        return "DESCARTAR", "1: falla G7"
    if por["G2"].value < min_authors / 2:
        return "DESCARTAR", f"2: G2 por debajo de {min_authors / 2:g} (la mitad de {min_authors} autores)"
    if {"G1", "G2"} <= falla:
        return "DESCARTAR", "3: fallan G1 y G2"
    if falla & {"G1", "G2", "G5"}:
        return "INVESTIGAR MÁS", "5: fallan G1, G2 o G5"
    if falla & {"G3", "G4", "G6"}:
        return "INVESTIGAR MÁS", "6: fallan G3, G4 o G6"
    if "G8" in falla:
        return "INVESTIGAR MÁS", "4: falla G8 (como máximo INVESTIGAR MÁS)"
    if coherencia is not None and not coherencia.measured:
        return "INVESTIGAR MÁS", "8: G0 sin comprobar (como máximo INVESTIGAR MÁS)"
    saturacion = por.get("G7")
    if saturacion is not None and not saturacion.measured and saturacion.evidence_ids:
        regla = (f"9: G7 con menciones favorables de menos de {MIN_AUTORES_COMPETIDOR} autores "
                 "(como máximo INVESTIGAR MÁS)")
        return "INVESTIGAR MÁS", regla
    return "CONSTRUIR", "7: pasan todas"


def judge_cluster(items: Sequence[EvidenceItem], labels: Mapping[str, VerifiedLabel], *,
                  now: datetime, min_authors: int = MIN_DISTINCT_AUTHORS,
                  contexto: Sequence[EvidenceItem] = (),
                  coherencia: GateResult | None = None) -> ClusterJudgement:
    """`coherencia`: G0 ya evaluada (coherencia.compuerta_coherencia); el juez del
    pipeline siempre la pasa. Sin ella no hay G0 (tests de compuertas sueltas)."""
    compuertas = ([coherencia] if coherencia else []) + evaluate_gates(
        items, labels, now=now, min_authors=min_authors, contexto=contexto)
    veredicto, regla = decide(compuertas, min_authors=min_authors)
    return ClusterJudgement(veredicto, [g.gate for g in compuertas if not g.passed], regla,
                            compuertas, score_cluster(items, labels, now=now, contexto=contexto))
