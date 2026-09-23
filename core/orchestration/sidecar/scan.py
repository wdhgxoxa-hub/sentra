"""Escaneo: `/api/scan`, `/api/scan/stream` (SSE) y `/api/scan/cancel`."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Mapping
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..graph import RadarDependencies
from ..state import RadarState
from .context import SidecarContext, is_reddit_fetcher
from .schemas import CancelRequest, CancelResponse, ScanRequest, ScanResponse

logger = logging.getLogger(__name__)


def _sse(payload: dict[str, Any]) -> str:
    """Serializa un evento en el formato `text/event-stream`."""
    return "data: " + json.dumps(payload, default=str) + "\n\n"


async def _persist(
    state: Mapping[str, Any],
    deps: RadarDependencies,
    postgres_dsn: str | None,
    status: str = "completed",
    data_source: str | None = None,
) -> tuple[str | None, bool, str | None]:
    """
    Vuelca el estado final en PostgreSQL.

    Corre en un hilo aparte a propósito. uvicorn impone un
    `ProactorEventLoop` en Windows y psycopg se niega a funcionar sobre él;
    `run_async` levanta un `SelectorEventLoop` propio en el hilo, que es
    compatible. Pelear con el bucle del servidor sería más frágil que
    aislarse de él.

    Un fallo aquí no invalida el escaneo: los datos ya están en LanceDB, así
    que se informa del motivo y se sigue. Perder el rastro relacional es
    molesto; perder la cosecha, mucho peor.

    Returns:
        `(run_id, persistido, motivo_del_fallo)`.
    """

    def _write() -> tuple[str | None, bool, str | None]:
        try:
            from core.storage.postgres_store import PostgresStore, run_async

            embedder = getattr(deps.store, "embedder", None)

            async def _inner() -> dict[str, Any]:
                async with PostgresStore(dsn=postgres_dsn) as store:
                    return await store.persist_state(
                        dict(state),
                        trigger_source="sidecar",
                        embedding_model=getattr(embedder, "name", None),
                        status=status,
                        data_source=data_source,
                    )

            summary = run_async(_inner())
            return summary.get("run_id"), True, None
        # Frontera con PostgreSQL: conexión, SQL y mapeo pueden fallar de
        # muchas formas y todas deben llegar al usuario como `persistError`.
        except Exception as exc:  # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"
            logger.error("No se pudo persistir en PostgreSQL: %s", detail)
            return None, False, detail

    return await asyncio.to_thread(_write)


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    @rutas.post("/api/scan", response_model=ScanResponse)
    async def scan(request: ScanRequest) -> ScanResponse:
        """
        Ejecuta el pipeline completo y, si procede, lo persiste.

        Los errores de un nodo concreto (una página que no descarga, un
        análisis que falla) viajan en `errors` y no tumban la petición: el
        grafo está diseñado para degradar la cosecha, no para abortarla.
        """
        es_reddit = is_reddit_fetcher(ctx.deps.fetcher)
        try:
            # Se pide el estado COMPLETO, no el resumen: persistir necesita
            # `signals` y `filtered_items`, que el resumen descarta.
            final_state = await ctx.pipeline.arun_state(
                subreddit=request.subreddit,
                limit=request.limit,
                sort=request.sort,
            )
        except Exception as exc:
            logger.exception("Fallo ejecutando el pipeline")
            raise HTTPException(status_code=500, detail=f"Fallo del pipeline: {exc}")

        should_persist = ctx.persist_default if request.persist is None else request.persist
        run_id: str | None = None
        persisted = False
        persist_error: str | None = None
        failure = final_state.get("failure") or None
        status = "failed" if failure else "completed"
        ctx.registrar_escaneo(es_reddit, final_state)

        fuente_datos = "reddit" if es_reddit else "demo"
        if should_persist:
            run_id, persisted, persist_error = await _persist(
                final_state, ctx.deps, ctx.postgres_dsn, status=status,
                data_source=fuente_datos,
            )

        result = ctx.pipeline.summarize(final_state)

        return ScanResponse(
            subreddit=request.subreddit,
            runId=run_id,
            cycles=int(result.get("cycles", 0)),
            stats=dict(result.get("stats") or {}),
            errors=list(result.get("errors") or []),
            qualified=list(result.get("qualified") or []),
            clusters=list(result.get("clusters") or []),
            qualifiedClusters=list(result.get("qualified_clusters") or []),
            persisted=persisted,
            persistError=persist_error,
            status=status,
            failureCode=failure["code"] if failure else None,
            retryAfterSeconds=failure.get("retryAfterSeconds") if failure else None,
            dataSource=fuente_datos,
            top=final_state.get("top"),
        )

    @rutas.post("/api/scan/cancel", response_model=CancelResponse)
    def cancel(request: CancelRequest) -> CancelResponse:
        """
        Solicita la interrupción de un escaneo.

        Es cooperativa: el grafo se corta ENTRE nodos, nunca a mitad de uno.
        Abortar un nodo a media escritura dejaría el almacén inconsistente,
        y lo cosechado hasta ese punto es válido y merece conservarse.

        Se admite cancelar un id que aún no ha arrancado: quien lanza el
        escaneo puede fijar el suyo, y entre la petición y el primer nodo
        hay tiempo de sobra para arrepentirse.
        """
        was_active = request.runId in ctx.active_runs
        ctx.cancelled_runs.add(request.runId)
        logger.info(
            "Cancelacion solicitada para %s (activo=%s)", request.runId, was_active
        )
        return CancelResponse(runId=request.runId, wasActive=was_active)

    @rutas.post("/api/scan/stream")
    async def scan_stream(request: ScanRequest) -> StreamingResponse:
        """
        Igual que `/api/scan`, pero emitiendo el avance nodo a nodo por SSE.

        Un escaneo puede durar minutos. Sin esto, la interfaz solo puede
        sondear, que es ruido para todas las capas y llega tarde igual.

        El `runId` se genera al abrir el flujo y viaja en todos los eventos:
        sin un identificador estable no se pueden correlacionar. El id de la
        ejecución en PostgreSQL, que solo existe tras persistir, viaja
        aparte en el evento final.
        """
        run_id = request.runId or str(uuid.uuid4())
        should_persist = ctx.persist_default if request.persist is None else request.persist
        es_reddit = is_reddit_fetcher(ctx.deps.fetcher)

        async def emitir() -> AsyncIterator[str]:
            ctx.active_runs.add(run_id)
            yield _sse({
                "type": "run:started",
                "runId": run_id,
                "subreddit": request.subreddit,
            })

            final_state: RadarState = {}
            cancelled = run_id in ctx.cancelled_runs
            try:
                if not cancelled:
                    async for kind, payload in ctx.pipeline.astream_state(
                        subreddit=request.subreddit,
                        limit=request.limit,
                        sort=request.sort,
                    ):
                        if kind == "node":
                            state = payload["state"]
                            final_state = state
                            yield _sse({
                                "type": "run:progress",
                                "runId": run_id,
                                "node": payload["node"],
                                "cycle": int(state.get("cycle", 0)) or 1,
                                "stats": dict(state.get("stats") or {}),
                            })
                            # Se comprueba ENTRE nodos: cortar a mitad de uno
                            # dejaría el almacén a medio escribir.
                            if run_id in ctx.cancelled_runs:
                                cancelled = True
                                break
                        else:
                            final_state = payload or RadarState()
            except Exception as exc:
                logger.exception("Fallo ejecutando el pipeline en streaming")
                ctx.forget(run_id)
                yield _sse({
                    "type": "run:error",
                    "runId": run_id,
                    "code": "internal_error",
                    "message": f"{type(exc).__name__}: {exc}",
                    "retryAfterSeconds": None,
                    "persistedRunId": None,
                    "persistError": None,
                })
                return

            failure = final_state.get("failure") or None
            if not cancelled:
                ctx.registrar_escaneo(es_reddit, final_state)
            if cancelled:
                status = "cancelled"
            elif failure:
                status = "failed"
            else:
                status = "completed"

            persisted_run_id = None
            persist_error = None
            if should_persist and final_state:
                # Un escaneo cancelado conserva lo cosechado, marcado como
                # tal: media cosecha sigue siendo información.
                persisted_run_id, _, persist_error = await _persist(
                    final_state,
                    ctx.deps,
                    ctx.postgres_dsn,
                    status=status,
                    data_source="reddit" if es_reddit else "demo",
                )

            result = ctx.pipeline.summarize(final_state)
            ctx.forget(run_id)
            if failure and not cancelled:
                # La fuente no entregó datos: es un fallo, no una cosecha
                # vacía. El código es estable; la interfaz lo traduce.
                yield _sse({
                    "type": "run:error",
                    "runId": run_id,
                    "code": failure["code"],
                    "message": failure["message"],
                    "retryAfterSeconds": failure.get("retryAfterSeconds"),
                    "persistedRunId": persisted_run_id,
                    "persistError": persist_error,
                })
                return
            yield _sse({
                "type": "run:cancelled" if cancelled else "run:finished",
                "runId": run_id,
                "persistedRunId": persisted_run_id,
                "persistError": persist_error,
                "qualified": len(result.get("qualified") or []),
                "clusters": len(result.get("qualified_clusters") or []),
                "stats": dict(result.get("stats") or {}),
                "errors": list(result.get("errors") or []),
                "dataSource": "reddit" if es_reddit else "demo",
                "top": final_state.get("top"),
            })

        return StreamingResponse(
            emitir(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                # Sin esto, un proxy intermedio podría retener el flujo y
                # entregarlo de golpe al final, que es justo lo contrario.
                "X-Accel-Buffering": "no",
            },
        )

    return rutas
