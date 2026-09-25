"""
Persistencia de un escaneo multifuente (F2.5)
=============================================

Orden obligado por las claves foráneas: primero toda la evidencia traída
(los duplicados también), después el crossposting que apunta a ella. Los
vectores se guardan solo de los canónicos, reutilizando los que calculó la
deduplicación. La ejecución se cierra con un error legible por fuente.

Una respuesta real de la API durante un escaneo verifica la fuente igual
que el botón «Probar»; un fallo la deja en error con su código.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from core.evidence.model import EvidenceItem

from .base import ProbeResult
from .dedup import Duplicate
from .registry import SourcesStateRepository
from .scan import MultiScanResult, SourceProgress


class EvidenceStore(Protocol):
    async def upsert_evidence(
        self, items: Sequence[EvidenceItem], run_id: str | None = None
    ) -> int: ...

    async def save_duplicates(self, duplicates: Sequence[Duplicate]) -> int: ...

    async def save_source_outcomes(self, run_id: str, outcomes: Sequence[SourceProgress]) -> int: ...

    async def finish_run(
        self, run_id: str, stats: dict[str, int], errors: Sequence[str] = (),
        status: str = "completed",
    ) -> None: ...

    async def purge_expired_evidence(self, source: str, days: int) -> list[str]: ...


class VectorStore(Protocol):
    def upsert(
        self, items: Sequence[EvidenceItem],
        vectors: Mapping[str, Sequence[float]] | None = None,
    ) -> int: ...

    def delete(self, ids: Sequence[str]) -> None: ...


def _error_de(progreso: SourceProgress) -> str:
    texto = f"{progreso.source}: {progreso.error_code}"
    return f"{texto} ({progreso.detail})" if progreso.detail else texto


async def persist_multiscan(
    store: EvidenceStore,
    run_id: str,
    result: MultiScanResult,
    *,
    vector_store: VectorStore | None = None,
    retention: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Guarda el escaneo y cierra su ejecución. Devuelve el resumen guardado.

    `retention` (fuente -> días) purga lo que esos términos no dejan guardar
    más tiempo sin refrescar (YouTube: 30 días), en la base y en los vectores.
    """
    await store.upsert_evidence(result.fetched, run_id=run_id)
    await store.save_duplicates(result.duplicates)
    if vector_store is not None:
        vector_store.upsert(result.items, vectors=result.vectors)
    purgados: list[str] = []
    for fuente, dias in (retention or {}).items():
        purgados += await store.purge_expired_evidence(fuente, dias)
    if purgados and vector_store is not None:
        vector_store.delete(purgados)

    fallidas = [p for p in result.per_source.values() if p.status == "failed"]
    errores = [_error_de(p) for p in fallidas]
    # Sin nada traído y con todas las fuentes caídas no hay escaneo que valga.
    todas_fallaron = bool(result.per_source) and len(fallidas) == len(result.per_source)
    if result.cancelled:
        estado = "cancelled"
    elif todas_fallaron and not result.fetched:
        estado = "failed"
    else:
        estado = "completed"
    # Cómo terminó cada fuente, motivo de parada incluido (Fase 1, B4; migración 018).
    await store.save_source_outcomes(run_id, list(result.per_source.values()))
    stats = {"fetched": len(result.fetched), "stored": len(result.fetched)}
    await store.finish_run(run_id, stats, errores, status=estado)
    return {"runId": run_id, "status": estado, "stored": len(result.fetched),
            "canonical": len(result.items), "duplicates": len(result.duplicates),
            "errors": errores, "purged": len(purgados)}


def record_source_outcomes(
    state: SourcesStateRepository,
    per_source: Mapping[str, SourceProgress],
    *,
    now: datetime | None = None,
) -> None:
    """Lo que dijo la API de cada fuente en el escaneo queda como su estado."""
    cuando = now or datetime.now(UTC)
    for progreso in per_source.values():
        if progreso.status == "failed":
            resultado = ProbeResult(ok=False, code=progreso.error_code,
                                    detail=progreso.detail or "", checked_at=cuando)
        elif progreso.requests == 0:
            # Sin ninguna petición no hubo respuesta de la API que verifique nada.
            continue
        else:
            resultado = ProbeResult(ok=True, checked_at=cuando,
                                    detail=f"Escaneo: {progreso.items} ítems")
        state.record_probe(progreso.source, resultado)
