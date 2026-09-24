"""
Juez, etapa 3: puntaje de nicho en siete dimensiones (D-M3)
===========================================================

Cada dimensión sale SOLO de conteos de evidencia etiquetada y verificada, y
lleva su cifra y sus ítems. Lo `undetermined` nunca suma.

- Frecuencia: dolores verificados (saturación 30).
- Convergencia: fuentes distintas entre los dolores; multiplicador principal,
  min(1, fuentes/3).
- Pago: ítems con wtp_signal o que buscan herramienta (saturación 5).
- Parches caseros: ítems con workaround_described (saturación 5).
- Hueco: menciones de competidores con queja frente a satisfechas; sin
  menciones, neutro (0,5) y marcado «sin_datos».
- Tendencia: crecimiento de la mitad reciente de la ventana frente a la
  antigua (saturación +100 %).
- Viabilidad para un desarrollador solo: `undetermined` en F3 (Fase 4).

puntaje = 100 · base · (0,5 + 0,5 · convergencia), con base la suma ponderada.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from core.evidence.model import EvidenceItem

from .labels import VerifiedLabel
from .quality import es_autopromocion

#: v2 (AUD2-001): mismos pesos; cambian las reglas que alimentan el puntaje
#: (lanzamientos fuera del dolor, G2 relativo al escaneo).
#: v5: G7 solo cuenta competidores nombrados por al menos 3 autores (regla 9).
#: v6: el contexto de G7 de cada pieza es solo su grupo más cercano.
WEIGHTS_VERSION = "judge-weights-v6"
#: D-M3. Suman 1.
WEIGHTS: dict[str, float] = {"frecuencia": 0.25, "pago": 0.25, "parches": 0.20,
                             "hueco": 0.15, "tendencia": 0.15}
FREQUENCY_SATURATION = 30
PAYMENT_SATURATION = 5
WORKAROUND_SATURATION = 5
#: +100 % de menciones entre las dos mitades de la ventana satura la tendencia.
TREND_SATURATION = 1.0
TREND_WINDOW_DAYS = 180
SOURCES_FOR_FULL_CONVERGENCE = 3
#: Sin menciones de competidores no hay datos del hueco: ni premio ni castigo.
NO_COMPETITION_EVIDENCE_GAP = 0.5


@dataclass(frozen=True)
class DimensionScore:
    name: str
    value: float | None
    normalized: float | None
    item_ids: list[str]
    note: str | None = None


@dataclass(frozen=True)
class NicheScore:
    score: float
    weights_version: str
    dimensions: list[DimensionScore]


#: «Show HN: …» / «Launch HN: …»: alguien anuncia lo que ha construido.
_LANZAMIENTO = re.compile(r"^\s*(?:show|launch)\s+hn\b", re.IGNORECASE)


def es_lanzamiento(item: EvidenceItem) -> bool:
    """Anuncio de un producto propio (AUD2-001): no es un dolor del mercado,
    ni una forma de apañárselas con él, ni una señal de pago, lo etiquete el
    LLM como lo etiquete. Sigue siendo evidencia (puede nombrar competidores)."""
    return bool(_LANZAMIENTO.match(item.title or ""))


def es_anuncio(item: EvidenceItem) -> bool:
    """Lanzamiento por el título o autopromoción/anuncio en el texto: señal de
    competencia (sigue en la evidencia y en el contexto de G7), nunca dolor."""
    return es_lanzamiento(item) or es_autopromocion(item.text)


def pain_items(items: Sequence[EvidenceItem], labels: Mapping[str, VerifiedLabel]) -> list[EvidenceItem]:
    """La evidencia que cuenta: miembros con dolor verificado que no son un lanzamiento."""
    return [i for i in items if labels.get(i.id) is not None and labels[i.id].is_pain == "yes"
            and not es_anuncio(i)]


def payment_items(items: Sequence[EvidenceItem], labels: Mapping[str, VerifiedLabel]) -> list[EvidenceItem]:
    return [i for i in items if (e := labels.get(i.id)) is not None and not es_anuncio(i)
            and (e.wtp_signal == "yes" or e.intent == "busca_herramienta")]


def workaround_items(items: Sequence[EvidenceItem],
                     labels: Mapping[str, VerifiedLabel]) -> list[EvidenceItem]:
    return [i for i in items if (e := labels.get(i.id)) is not None and not es_anuncio(i)
            and e.workaround_described == "yes"]


def _saturada(valor: float, tope: float) -> float:
    return min(1.0, valor / tope) if tope else 0.0


def _hueco(items: Sequence[EvidenceItem], labels: Mapping[str, VerifiedLabel]) -> DimensionScore:
    quejas, satisfechos, ids = 0, 0, []
    for item in items:
        etiqueta = labels.get(item.id)
        for competidor in etiqueta.competitors if etiqueta else []:
            if competidor.stance == "queja":
                quejas += 1
            elif competidor.stance == "satisfecho":
                satisfechos += 1
            else:
                continue
            ids.append(item.id)
    if quejas + satisfechos == 0:
        return DimensionScore("hueco", None, NO_COMPETITION_EVIDENCE_GAP, [], "sin_datos")
    return DimensionScore("hueco", quejas, quejas / (quejas + satisfechos), sorted(set(ids)))


def _tendencia(dolores: Sequence[EvidenceItem], now: datetime) -> DimensionScore:
    mitad = now - timedelta(days=TREND_WINDOW_DAYS / 2)
    inicio = now - timedelta(days=TREND_WINDOW_DAYS)
    recientes = [i for i in dolores if i.created_at >= mitad]
    antiguos = [i for i in dolores if inicio <= i.created_at < mitad]
    crecimiento = (len(recientes) - len(antiguos)) / max(len(antiguos), 1)
    return DimensionScore("tendencia", crecimiento, _saturada(max(crecimiento, 0.0), TREND_SATURATION),
                          sorted(i.id for i in recientes + antiguos))


def score_cluster(items: Sequence[EvidenceItem], labels: Mapping[str, VerifiedLabel], *,
                  now: datetime, contexto: Sequence[EvidenceItem] = ()) -> NicheScore:
    """`contexto`: la evidencia sin dolor cercana al grupo. Como en G7, cuenta
    para la competencia (hueco): la dimensión y la compuerta leen lo mismo."""
    dolores = pain_items(items, labels)
    fuentes = sorted({i.source for i in dolores})
    pago, parches = payment_items(items, labels), workaround_items(items, labels)
    dimensiones = [
        DimensionScore("frecuencia", len(dolores), _saturada(len(dolores), FREQUENCY_SATURATION),
                       sorted(i.id for i in dolores)),
        DimensionScore("convergencia", len(fuentes),
                       _saturada(len(fuentes), SOURCES_FOR_FULL_CONVERGENCE),
                       sorted(i.id for i in dolores)),
        DimensionScore("pago", len(pago), _saturada(len(pago), PAYMENT_SATURATION),
                       sorted(i.id for i in pago)),
        DimensionScore("parches", len(parches), _saturada(len(parches), WORKAROUND_SATURATION),
                       sorted(i.id for i in parches)),
        _hueco([*items, *contexto], labels),
        _tendencia(dolores, now),
        DimensionScore("viabilidad", None, None, [], "undetermined"),
    ]
    por_nombre = {d.name: d for d in dimensiones}
    base = sum(peso * (por_nombre[nombre].normalized or 0.0) for nombre, peso in WEIGHTS.items())
    convergencia = por_nombre["convergencia"].normalized or 0.0
    return NicheScore(100 * base * (0.5 + 0.5 * convergencia), WEIGHTS_VERSION, dimensiones)
