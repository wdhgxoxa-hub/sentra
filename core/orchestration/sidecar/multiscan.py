"""Escaneo multifuente por SSE: progreso por fuente, estado verificado y persistencia."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

import psycopg
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.evidence.author import load_or_create_salt
from core.sources import http as fuentes_http
from core.sources.catalog import SOURCES
from core.sources.persist import persist_multiscan, record_source_outcomes
from core.sources.profile import ScanProfile
from core.sources.registry import active_sources, credentials_for
from core.sources.scan import MultiScanResult, SourceProgress, run_multisource_scan

from .context import SidecarContext, load_dotenv
from .migrations import pending_detail
from .schemas import CancelRequest, CancelResponse
from .sources import commercial_mode

logger = logging.getLogger(__name__)

TRIGGER_SOURCE = "multifuente"


def _sse(payload: dict[str, Any]) -> str:
    """Serializa un evento en el formato `text/event-stream`."""
    return "data: " + json.dumps(payload, default=str) + "\n\n"


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
                await persist_multiscan(
                    store, run_id, resultado, vector_store=vectores,
                    retention={c.id: c.retention_days for c in SOURCES if c.retention_days})

        run_async(guardar())
        return None
    except Exception as exc:  # noqa: BLE001 - frontera con PostgreSQL y LanceDB
        logger.error("No se pudo guardar el escaneo multifuente: %s", type(exc).__name__)
        return f"{type(exc).__name__}: {exc}"


def _proveedor_del_juez(ctx: SidecarContext) -> tuple[Any, str | None, str | None]:
    """(proveedor, modelo, motivo). Sin Gemini, el juez corre sin proveedor:
    todo queda undetermined y nada sale CONSTRUIR."""
    try:
        from core.llm.budget import LLMBudget
        from core.llm.gemini import GeminiProvider

        clave, modelo = ctx.resolver_modelo("defecto")
        return GeminiProvider(clave, budget=LLMBudget()), modelo, None
    except Exception as exc:  # noqa: BLE001 - sin Gemini el juez sigue, sin etiquetas
        return None, None, getattr(exc, "code", type(exc).__name__)


def _juzgar(ctx: SidecarContext, run_id: str, resultado: MultiScanResult) -> dict[str, Any]:
    """Juez completo sobre lo guardado; devuelve su resumen. En un hilo aparte."""
    import os
    from datetime import UTC, datetime

    from core.judge.pipeline import run_judge
    from core.judge.store import PostgresLabelCache, previous_identities
    from core.storage.postgres_store import (
        DEFAULT_DSN,
        DSN_ENV_VAR,
        PostgresStore,
        run_async,
    )

    dsn = ctx.postgres_dsn or os.environ.get(DSN_ENV_VAR) or DEFAULT_DSN
    proveedor, modelo, motivo = _proveedor_del_juez(ctx)

    async def juzgar() -> dict[str, Any]:
        async with PostgresStore(dsn=dsn) as store:
            previos = await previous_identities(store)
            juicio = run_judge(resultado.items, resultado.vectors, provider=proveedor, model=modelo,
                               cache=PostgresLabelCache(dsn), now=datetime.now(UTC),
                               previous=previos)
            await store.save_verdicts(run_id, juicio.verdicts)
            return juicio.summary

    resumen = run_async(juzgar())
    resumen["llm"] = {"model": modelo, "unavailable": motivo,
                      "calls": len(getattr(proveedor, "usage", []) or [])}
    return resumen


def _nuevo_id() -> str:
    """Id de un escaneo que no se guarda (sin ejecución en PostgreSQL)."""
    return uuid.uuid4().hex


def _resumen_fuente(progreso: SourceProgress) -> dict[str, Any]:
    return {"status": progreso.status, "items": progreso.items,
            "errorCode": progreso.error_code, "detail": progreso.detail,
            "stopReason": progreso.stop_reason, "requests": progreso.requests,
            "units": progreso.units, "usd": progreso.usd}


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    @rutas.post("/api/scan/cancel", response_model=CancelResponse)
    def cancel(request: CancelRequest) -> CancelResponse:
        """
        Solicita la interrupción de un escaneo multifuente.

        Es cooperativa: cada fuente la mira entre páginas, y lo traído hasta
        ese punto se conserva. Se admite cancelar un id que aún no ha
        arrancado: entre la petición y la primera página hay tiempo de sobra
        para arrepentirse.
        """
        was_active = request.runId in ctx.active_runs
        ctx.cancelled_runs.add(request.runId)
        logger.info("Cancelacion solicitada para %s (activo=%s)", request.runId, was_active)
        return CancelResponse(runId=request.runId, wasActive=was_active)

    @rutas.post("/api/sources/scan/stream")
    async def multiscan_stream(request: MultiScanRequest) -> StreamingResponse:
        perfil = request.profile
        persistir = ctx.persist_default if request.persist is None else request.persist

        async def emitir() -> AsyncIterator[str]:
            env = dict(load_dotenv(ctx.env_path, env={}))
            try:
                activas = await asyncio.to_thread(
                    active_sources, SOURCES, env, ctx.sources_state, commercial_mode(env))
            except psycopg.errors.UndefinedTable:
                detalle = await asyncio.to_thread(pending_detail, ctx)
                yield _sse({"type": "error", "code": "migrations_pending", "message": detalle})
                return
            if not activas:
                yield _sse({"type": "error", "code": "no_active_sources",
                            "message": "No hay ninguna fuente activa."})
                return

            run_id, error_persistencia = None, None
            if persistir:
                run_id, error_persistencia = await asyncio.to_thread(
                    _abrir_ejecucion, ctx, perfil)
            # Con ejecución, su id: así /api/scan/cancel y cancel_scan (que
            # además la marca en PostgreSQL) sirven igual que en la pipeline.
            scan_id = run_id or _nuevo_id()
            ctx.active_runs.add(scan_id)
            cola: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

            async def trabajo() -> None:
                """Escaneo, estado y guardado. Vive fuera de la conexión: si
                el cliente se va, el escaneo termina y su ejecución se cierra
                de verdad en lugar de quedarse en `running`."""
                try:
                    salt = load_or_create_salt(ctx.env_path)
                    vectores = ctx.evidence_vectors() if ctx.evidence_vectors else None
                    async with fuentes_http.new_client() as cliente:
                        adaptadores = [
                            clase(http=cliente, budget=clase.default_budget(),
                                  credentials=credentials_for(clase, env), author_salt=salt)
                            for clase in activas
                        ]
                        resultado = await run_multisource_scan(
                            adaptadores, perfil.to_query(), on_event=cola.put_nowait,
                            embed=vectores.embed if vectores else None,
                            should_stop=lambda: scan_id in ctx.cancelled_runs)
                    await asyncio.to_thread(record_source_outcomes, ctx.sources_state,
                                            resultado.per_source)
                    error = error_persistencia
                    guardado = False
                    if run_id is not None:
                        error = await asyncio.to_thread(_guardar, ctx, run_id, resultado)
                        guardado = error is None
                    cola.put_nowait({
                        "type": "scan:done", "runId": run_id, "cancelled": resultado.cancelled,
                        "persisted": guardado, "persistError": error,
                        "fetched": len(resultado.fetched), "canonical": len(resultado.items),
                        "duplicates": len(resultado.duplicates),
                        "perSource": {s: _resumen_fuente(p)
                                      for s, p in resultado.per_source.items()},
                    })
                    # El juez necesita lo guardado: sin persistencia no hay veredictos.
                    if guardado and run_id is not None:
                        cola.put_nowait({"type": "judge:started", "runId": run_id})
                        try:
                            resumen = await asyncio.to_thread(_juzgar, ctx, run_id, resultado)
                            cola.put_nowait({"type": "judge:done", "runId": run_id,
                                             "summary": resumen})
                        # El escaneo ya está guardado: un fallo del juez se cuenta, no lo tumba.
                        except Exception as exc:
                            logger.exception("Fallo del juez tras el escaneo")
                            cola.put_nowait({"type": "judge:error", "runId": run_id,
                                             "code": "internal_error",
                                             "message": type(exc).__name__})
                # Frontera de la tarea: un fallo aquí debe llegar a la interfaz
                # como evento, no perderse en una tarea que nadie espera.
                except Exception as exc:
                    logger.exception("Fallo en el escaneo multifuente")
                    cola.put_nowait({"type": "error", "code": "internal_error",
                                     "message": type(exc).__name__})
                finally:
                    ctx.forget(scan_id)
                    cola.put_nowait(None)

            tarea = asyncio.create_task(trabajo())
            # Referencia fuerte: una tarea sin referencias puede recogerse a medias.
            ctx.background_tasks.add(tarea)
            tarea.add_done_callback(ctx.background_tasks.discard)

            yield _sse({"type": "scan:started", "scanId": scan_id, "runId": run_id,
                        "sources": [f.id for f in activas]})
            while (evento := await cola.get()) is not None:
                yield _sse(evento)

        return StreamingResponse(emitir(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    return rutas
