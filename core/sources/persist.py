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

    async def finish_run(
        self, run_id: str, stats: dict[str, int], errors: Sequence[str] = (),
        status: str = "completed",
    ) -> None: ...


class VectorStore(Protocol):
    def upsert(
        self, items: Sequence[EvidenceItem],
        vectors: Mapping[str, Sequence[float]] | None = None,
    ) -> int: ...


def _error_de(progreso: SourceProgress) -> str:
    texto = f"{progreso.source}: {progreso.error_code}"
    return f"{texto} ({progreso.detail})" if progreso.detail else texto


async def persist_multiscan(
    store: EvidenceStore,
    run_id: str,
    result: MultiScanResult,
    *,
    vector_store: VectorStore | None = None,
) -> dict[str, Any]:
    """Guarda el escaneo y cierra su ejecución. Devuelve el resumen guardado."""
    await store.upsert_evidence(result.fetched, run_id=run_id)
    await store.save_duplicates(result.duplicates)
    if vector_store is not None:
        vector_store.upsert(result.items, vectors=result.vectors)

    fallidas = [p for p in result.per_source.values() if p.status == "failed"]
    errores = [_error_de(p) for p in fallidas]
    # Sin nada traído y con todas las fuentes caídas no hay escaneo que valga.
    todas_fallaron = bool(result.per_source) and len(fallidas) == len(result.per_source)
    estado = "failed" if todas_fallaron and not result.fetched else "completed"
    stats = {"fetched": len(result.fetched), "stored": len(result.fetched)}
    await store.finish_run(run_id, stats, errores, status=estado)
    return {"runId": run_id, "status": estado, "stored": len(result.fetched),
            "canonical": len(result.items), "duplicates": len(result.duplicates),
            "errors": errores}


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
