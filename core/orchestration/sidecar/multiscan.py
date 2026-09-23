"""Escaneo multifuente por SSE: progreso por fuente, estado verificado y persistencia."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.evidence.author import load_or_create_salt
from core.sources import http as fuentes_http
from core.sources.budget import SourceBudget
from core.sources.catalog import SOURCES
from core.sources.persist import persist_multiscan, record_source_outcomes
from core.sources.profile import ScanProfile
from core.sources.registry import active_sources, credentials_for
from core.sources.scan import MultiScanResult, SourceProgress, run_multisource_scan

from .context import SidecarContext, load_dotenv
from .scan import _sse
from .sources import commercial_mode

logger = logging.getLogger(__name__)

TRIGGER_SOURCE = "multifuente"


class MultiScanRequest(BaseModel):
    profile: ScanProfile
    persist: bool | None = None


def _abrir_ejecucion(ctx: SidecarContext, perfil: ScanProfile) -> tuple[str | None, str | None]:
    """(run_id, motivo del fallo). En un hilo: psycopg no funciona sobre el
    ProactorEventLoop que uvicorn impone en Windows."""
    try:
        from core.storage.postgres_store import PostgresStore, run_async

        async def abrir() -> str:
            async with PostgresStore(dsn=ctx.postgres_dsn) as store:
                return await store.start_run(
                    perfil.name, trigger_source=TRIGGER_SOURCE,
                    parameters=perfil.model_dump(mode="json"), data_source="real")

        return run_async(abrir()), None
    except Exception as exc:  # noqa: BLE001 - frontera con PostgreSQL
        logger.error("No se pudo abrir la ejecución multifuente: %s", type(exc).__name__)
        return None, f"{type(exc).__name__}: {exc}"


def _guardar(ctx: SidecarContext, run_id: str, resultado: MultiScanResult) -> str | None:
    """Motivo del fallo, o None si se guardó todo."""
    try:
        from core.storage.postgres_store import PostgresStore, run_async

        salt = load_or_create_salt(ctx.env_path)
        vectores = ctx.evidence_vectors() if ctx.evidence_vectors else None

        async def guardar() -> None:
            async with PostgresStore(dsn=ctx.postgres_dsn, author_salt=salt) as store:
                await persist_multiscan(store, run_id, resultado, vector_store=vectores)

        run_async(guardar())
        return None
    except Exception as exc:  # noqa: BLE001 - frontera con PostgreSQL y LanceDB
        logger.error("No se pudo guardar el escaneo multifuente: %s", type(exc).__name__)
        return f"{type(exc).__name__}: {exc}"


def _resumen_fuente(progreso: SourceProgress) -> dict[str, Any]:
    return {"status": progreso.status, "items": progreso.items,
            "errorCode": progreso.error_code, "detail": progreso.detail,
            "stopReason": progreso.stop_reason, "requests": progreso.requests,
            "units": progreso.units, "usd": progreso.usd}


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    @rutas.post("/api/sources/scan/stream")
    async def multiscan_stream(request: MultiScanRequest) -> StreamingResponse:
        perfil = request.profile
        persistir = ctx.persist_default if request.persist is None else request.persist

        async def emitir() -> AsyncIterator[str]:
            env = dict(load_dotenv(ctx.env_path, env={}))
            activas = await asyncio.to_thread(
                active_sources, SOURCES, env, ctx.sources_state, commercial_mode(env))
            if not activas:
                yield _sse({"type": "error", "code": "no_active_sources",
                            "message": "No hay ninguna fuente activa."})
                return

            run_id, error_persistencia = None, None
            if persistir:
                run_id, error_persistencia = await asyncio.to_thread(
                    _abrir_ejecucion, ctx, perfil)
            yield _sse({"type": "scan:started", "runId": run_id,
                        "sources": [f.id for f in activas]})

            cola: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
            salt = load_or_create_salt(ctx.env_path)
            vectores = ctx.evidence_vectors() if ctx.evidence_vectors else None

            async def escanear() -> MultiScanResult:
                try:
                    async with fuentes_http.new_client() as cliente:
                        adaptadores = [
                            clase(http=cliente, budget=SourceBudget(source=clase.id),
                                  credentials=credentials_for(clase, env), author_salt=salt)
                            for clase in activas
                        ]
                        return await run_multisource_scan(
                            adaptadores, perfil.to_query(), on_event=cola.put_nowait,
                            embed=vectores.embed if vectores else None)
                finally:
                    cola.put_nowait(None)

            tarea = asyncio.create_task(escanear())
            try:
                while (evento := await cola.get()) is not None:
                    yield _sse(evento)
                resultado = await tarea
            finally:
                # El cliente cerró la conexión: no se deja el escaneo huérfano.
                if not tarea.done():
                    tarea.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await tarea

            await asyncio.to_thread(record_source_outcomes, ctx.sources_state,
                                    resultado.per_source)
            guardado = False
            if run_id is not None:
                error_persistencia = await asyncio.to_thread(_guardar, ctx, run_id, resultado)
                guardado = error_persistencia is None
            yield _sse({
                "type": "scan:done", "runId": run_id,
                "persisted": guardado, "persistError": error_persistencia,
                "fetched": len(resultado.fetched), "canonical": len(resultado.items),
                "duplicates": len(resultado.duplicates),
                "perSource": {s: _resumen_fuente(p) for s, p in resultado.per_source.items()},
            })

        return StreamingResponse(emitir(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    return rutas
