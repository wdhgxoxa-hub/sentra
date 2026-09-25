"""
Estimación del gasto de Gemini de un escaneo (Fase 1, B4)
=========================================================

Antes de escanear no se sabe cuántas piezas pasarán el filtro: se da un
rango, siempre marcado como «estimado».

- Llamadas: de 0 (nada pasa el filtro) a ⌈tope de etiquetas / 20⌉ lotes de
  etiquetado + 1 G0 + 2 confirmaciones de subgrupos + 1 abogado, sin pasar
  del tope por escaneo ni de lo que queda hoy. Los reintentos no se estiman:
  si hacen falta, los corta el propio tope.
- Tokens: esas llamadas por la media de cada propósito en llm_usage (lo que
  salió bien); sin historial, SIN_HISTORIAL_TOKENS por llamada, el techo de lo
  medido en el etiquetado (13 000–23 000 por lote, tasks/plan-fuentes-y-e8.md).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from .control import Topes

LOTE_DE_ETIQUETADO = 20  # core.judge.labels.BATCH_SIZE (un test lo vigila)
LLAMADAS_G0 = 1 + 2  # la comprobación del escaneo y hasta 2 confirmaciones de subgrupos
LLAMADAS_ABOGADO = 1
SIN_HISTORIAL_TOKENS = 25_000


@dataclass(frozen=True)
class Estimacion:
    llamadas_min: int
    llamadas_max: int
    tokens_min: int
    tokens_max: int
    gastado_hoy: tuple[int, int]
    queda_hoy: tuple[int, int]
    con_historial: bool

    @property
    def puede_escanear(self) -> bool:
        return self.queda_hoy[0] > 0 and self.queda_hoy[1] > 0


def estimar(topes: Topes, *, uso_hoy: tuple[int, int], medias: Mapping[str, float],
            tope_etiquetas: int) -> Estimacion:
    por_proposito = {
        "etiquetado": math.ceil(max(0, tope_etiquetas) / LOTE_DE_ETIQUETADO),
        "g0": LLAMADAS_G0,
        "abogado": LLAMADAS_ABOGADO,
    }
    queda = (max(0, topes.daily_calls - uso_hoy[0]), max(0, topes.daily_tokens - uso_hoy[1]))
    todas = sum(por_proposito.values())
    llamadas = min(todas, topes.scan_calls, queda[0])
    tokens_todas = sum(n * medias.get(p, SIN_HISTORIAL_TOKENS) for p, n in por_proposito.items())
    # Si un tope recorta las llamadas, los tokens se recortan en proporción.
    tokens = 0 if llamadas == 0 else min(round(tokens_todas * llamadas / todas), topes.scan_tokens, queda[1])
    return Estimacion(0, llamadas, 0, tokens, uso_hoy, queda,
                      con_historial=any(p in medias for p in por_proposito))
