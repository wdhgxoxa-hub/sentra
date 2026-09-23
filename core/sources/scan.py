"""
Escaneo multifuente en paralelo (F2.5)
======================================

Cada fuente activa corre en su propia tarea, con su presupuesto. Reglas:

- El fallo de una fuente se registra con su código y NO detiene a las
  demás. Lo que trajo antes de fallar es evidencia real y se conserva.
- Un presupuesto agotado no es un fallo: la fuente termina con ese motivo.
- Al final se deduplica entre fuentes (F2.6): el crossposting no es
  corroboración.

Los eventos (`source:started`, `source:progress`, `source:done`,
`source:error`) alimentan el progreso por fuente de la interfaz.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from core.evidence.model import EvidenceItem, SearchQuery

from .base import SourceAdapter
from .dedup import Duplicate, deduplicate
from .errors import SourceBudgetExhausted, SourceError

logger = logging.getLogger(__name__)

EventSink = Callable[[dict[str, Any]], Awaitable[None] | None]
Embedder = Callable[[Sequence[EvidenceItem]], Mapping[str, Sequence[float]]]

#: Cada cuántos ítems se avisa del progreso de una fuente.
PROGRESS_EVERY = 10


@dataclass
class SourceProgress:
    source: str
    status: Literal["running", "done", "failed"] = "running"
    items: int = 0
    error_code: str | None = None
    detail: str | None = None
    stop_reason: str | None = None
    requests: int = 0
    units: float = 0.0
    usd: float = 0.0


@dataclass
class MultiScanResult:
    items: list[EvidenceItem] = field(default_factory=list)
    duplicates: list[Duplicate] = field(default_factory=list)
    per_source: dict[str, SourceProgress] = field(default_factory=dict)


async def _emitir(sink: EventSink | None, evento: dict[str, Any]) -> None:
    if sink is None:
        return
    resultado = sink(evento)
    if inspect.isawaitable(resultado):
        await resultado


async def _escanear(
    fuente: SourceAdapter, query: SearchQuery, sink: EventSink | None
) -> tuple[SourceProgress, list[EvidenceItem]]:
    progreso = SourceProgress(fuente.id)
    items: list[EvidenceItem] = []
    await _emitir(sink, {"type": "source:started", "source": fuente.id})
    try:
        async for item in fuente.search(query):
            items.append(item)
            progreso.items = len(items)
            if progreso.items % PROGRESS_EVERY == 0:
                await _emitir(sink, {"type": "source:progress", "source": fuente.id,
                                     "items": progreso.items})
        progreso.status = "done"
    except SourceBudgetExhausted as exc:
        progreso.status, progreso.stop_reason, progreso.detail = "done", exc.code, exc.detail
    except SourceError as exc:
        progreso.status, progreso.error_code, progreso.detail = "failed", exc.code, exc.detail
    # Frontera con cada adaptador: un fallo de programación en una fuente no
    # puede tumbar el escaneo de las demás.
    except Exception as exc:
        logger.exception("Fallo inesperado en la fuente %s", fuente.id)
        progreso.status, progreso.error_code = "failed", "internal_error"
        progreso.detail = type(exc).__name__
    progreso.requests = fuente.budget.spent_requests
    progreso.units = fuente.budget.spent_units
    progreso.usd = fuente.budget.spent_usd

    evento: dict[str, Any] = {"type": "source:done" if progreso.status == "done" else "source:error",
                              "source": fuente.id, "items": progreso.items}
    if progreso.status == "failed":
        evento |= {"code": progreso.error_code, "detail": progreso.detail}
    elif progreso.stop_reason:
        evento["stopReason"] = progreso.stop_reason
    await _emitir(sink, evento)
    return progreso, items


async def run_multisource_scan(
    fuentes: Sequence[SourceAdapter],
    query: SearchQuery,
    *,
    on_event: EventSink | None = None,
    embed: Embedder | None = None,
) -> MultiScanResult:
    """Escanea todas las fuentes a la vez y deduplica lo que traen."""
    resultados = await asyncio.gather(*(_escanear(f, query, on_event) for f in fuentes))
    resultado = MultiScanResult()
    todos: list[EvidenceItem] = []
    for progreso, items in resultados:
        resultado.per_source[progreso.source] = progreso
        todos.extend(items)
    vectores = embed(todos) if embed is not None and todos else {}
    limpio = deduplicate(todos, vectores)
    resultado.items, resultado.duplicates = limpio.canonical, limpio.duplicates
    return resultado
