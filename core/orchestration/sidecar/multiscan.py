"""Escaneo multifuente por SSE: progreso por fuente, estado verificado y persistencia."""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import os
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.evidence.author import load_or_create_salt
from core.llm.control import ControlDeGemini
from core.llm.estimacion import Estimacion, estimar
from core.sources import http as fuentes_http
from core.sources.catalog import SOURCES
from core.sources.encaje import fuentes_omitidas
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
#: Sin eventos durante este rato (el juez puede tardar minutos), el flujo manda
#: un comentario SSE: la interfaz corta solo tras un silencio largo, nunca por
#: la duración total de un escaneo vivo (AUD2-025).
KEEPALIVE_S = 15.0
#: Tope de piezas que el juez etiqueta por escaneo (20 por llamada a Gemini):
#: así se reparte un presupuesto de llamadas. Vacío o inválido: el de siempre.
JUEZ_MAX_ETIQUETAS_ENV = "RIR_JUEZ_MAX_ETIQUETAS"


def _tope_de_etiquetas() -> int:
    from core.judge.labels import MAX_ITEMS_PER_SCAN

    valor = os.environ.get(JUEZ_MAX_ETIQUETAS_ENV, "").strip()
    if not valor:
        return MAX_ITEMS_PER_SCAN
    try:
        tope = int(valor)
    except ValueError:
        logger.warning("%s=%r no es un número; se usa %d", JUEZ_MAX_ETIQUETAS_ENV, valor, MAX_ITEMS_PER_SCAN)
        return MAX_ITEMS_PER_SCAN
    return max(0, tope)


def _sse(payload: dict[str, Any]) -> str:
    """Serializa un evento en el formato `text/event-stream`."""
    return "data: " + json.dumps(payload, default=str) + "\n\n"


class MultiScanRequest(BaseModel):
    profile: ScanProfile
    persist: bool | None = None
    #: El identificador de /api/scan/estimate: sin él no se escanea (Fase 1, B4).
    confirmation: str | None = None


class EstimateRequest(BaseModel):
    profile: ScanProfile


#: Lo que vale una estimación confirmada: pasado este rato, hay que volver a estimar.
CONFIRMACION_VALIDA_S = 600.0
_MENSAJES_CONFIRMACION = {
    "scan_confirmation_required": "Antes de escanear hay que ver y confirmar la estimación de Gemini.",
    "scan_confirmation_used": "Esa confirmación ya se usó: cada escaneo se confirma una vez.",
    "scan_confirmation_expired": "La confirmación caducó: vuelve a ver la estimación y confírmala.",
    "scan_confirmation_mismatch": "La confirmación es de otro perfil: confirma la estimación de este.",
}


def _huella_perfil(perfil: ScanProfile) -> str:
    return hashlib.sha256(perfil.model_dump_json().encode()).hexdigest()


def _usar_confirmacion(ctx: SidecarContext, confirmacion: str | None, perfil: ScanProfile) -> str | None:
    """El código del rechazo, o None si la confirmación vale (y queda usada)."""
    if confirmacion is not None and confirmacion in ctx.confirmaciones_usadas:
        return "scan_confirmation_used"
    if confirmacion is None or confirmacion not in ctx.confirmaciones:
        return "scan_confirmation_required"
    huella, creada = ctx.confirmaciones[confirmacion]
    if time.monotonic() - creada > CONFIRMACION_VALIDA_S:
        del ctx.confirmaciones[confirmacion]
        return "scan_confirmation_expired"
    if huella != _huella_perfil(perfil):
        return "scan_confirmation_mismatch"
    del ctx.confirmaciones[confirmacion]
    ctx.confirmaciones_usadas.add(confirmacion)
    return None


def _estimacion(ctx: SidecarContext) -> Estimacion:
    """Estimación con los topes, lo gastado hoy y las medias de llm_usage. En un hilo."""
    registro = ctx.registro_de_uso
    return estimar(registro.topes(), uso_hoy=registro.uso_de_hoy(datetime.now(UTC)),
                   medias=registro.medias_de_tokens(), tope_etiquetas=_tope_de_etiquetas())


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

        vectores = ctx.evidence_vectors() if ctx.evidence_vectors else None

        async def guardar() -> None:
            async with PostgresStore(dsn=ctx.postgres_dsn) as store:
                await persist_multiscan(
                    store, run_id, resultado, vector_store=vectores,
                    retention={c.id: c.retention_days for c in SOURCES if c.retention_days})

        run_async(guardar())
        return None
    except Exception as exc:  # noqa: BLE001 - frontera con PostgreSQL y LanceDB
        logger.error("No se pudo guardar el escaneo multifuente: %s", type(exc).__name__)
        return f"{type(exc).__name__}: {exc}"


def _proveedor_del_juez(ctx: SidecarContext, control: ControlDeGemini) -> tuple[Any, str | None, str | None]:
    """(proveedor, modelo, motivo). Sin Gemini, el juez corre sin proveedor:
    todo queda undetermined y nada sale CONSTRUIR. Cada llamada pasa por
    `control` (una fila de llm_usage por intento)."""
    try:
        from core.llm.gemini import GeminiProvider

        clave, modelo = ctx.resolver_modelo("defecto")
        return GeminiProvider(clave, control=control), modelo, None
    except Exception as exc:  # noqa: BLE001 - sin Gemini el juez sigue, sin etiquetas
        motivo = getattr(exc, "code", type(exc).__name__)
        # AUD-051: se degrada, pero no en silencio: queda en el log y el motivo
        # viaja en el resumen del juez hasta la interfaz.
        logger.warning("El juez corre sin Gemini: %s", motivo)
        return None, None, motivo


def _juzgar(ctx: SidecarContext, run_id: str, resultado: MultiScanResult, *,
            tema: Sequence[str] = (), descripcion: str = "") -> dict[str, Any]:
    """Juez completo sobre lo guardado; devuelve su resumen. En un hilo aparte.
    `tema`: palabras clave del perfil; no nombran nichos (AUD2-001)."""
    from datetime import UTC, datetime

    from core.judge.pipeline import run_judge
    from core.judge.store import (
        PostgresCoherenceCache,
        PostgresLabelCache,
        guardar_resumen_del_juez,
        marcar_juzgada,
        marcar_parada,
        previous_identities,
    )
    from core.storage.postgres_store import (
        PostgresStore,
        resolver_dsn,
        run_async,
    )

    dsn = resolver_dsn(ctx.postgres_dsn)
    control = ctx.control(run_id, escaneo=True)
    proveedor, modelo, motivo = _proveedor_del_juez(ctx, control)

    async def juzgar() -> dict[str, Any]:
        async with PostgresStore(dsn=dsn) as store:
            previos = await previous_identities(store)
            almacen = ctx.evidence_vectors() if ctx.evidence_vectors else None
            juicio = run_judge(resultado.items, resultado.vectors, provider=proveedor, model=modelo,
                               cache=PostgresLabelCache(dsn), now=datetime.now(UTC),
                               vectores_frase=almacen.embed_frases if almacen else (lambda _f: {}),
                               previous=previos, tema=tema, descripcion=descripcion,
                               label_max_items=_tope_de_etiquetas(),
                               coherence_cache=PostgresCoherenceCache(dsn))
            await store.save_verdicts(run_id, juicio.verdicts)
            await marcar_juzgada(store, run_id, construir=sum(
                1 for v in juicio.verdicts if v["verdict"] == "CONSTRUIR"))
            # Un tope de Gemini cortó el juez: el motivo de parada queda en la ejecución.
            if control.motivo_de_corte:
                await marcar_parada(store, run_id, control.motivo_de_corte)
            resumen = dict(juicio.summary)
            resumen["llm"] = {"model": modelo, "unavailable": motivo,
                              "calls": len(getattr(proveedor, "usage", []) or []),
                              "stopReason": control.motivo_de_corte}
            # El resumen queda con la ejecución (migración 019), no solo en judge:done.
            await guardar_resumen_del_juez(store, run_id, resumen)
            return resumen

    return run_async(juzgar())


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

    @rutas.post("/api/scan/estimate")
    async def scan_estimate(request: EstimateRequest) -> dict[str, Any]:
        """Llamadas y tokens estimados del escaneo, lo gastado hoy y lo que queda,
        con el identificador que el escaneo exige (un solo uso, caduca)."""
        try:
            e = await asyncio.to_thread(_estimacion, ctx)
        except psycopg.errors.UndefinedTable:
            detalle = await asyncio.to_thread(pending_detail, ctx)
            raise HTTPException(status_code=503, detail={"code": "migrations_pending",
                                                         "detail": detalle}) from None
        identificador = uuid.uuid4().hex
        ctx.confirmaciones[identificador] = (_huella_perfil(request.profile), time.monotonic())
        return {
            "confirmationId": identificador,
            "expiresInS": CONFIRMACION_VALIDA_S,
            "estimate": {
                "estimated": True,
                "calls": {"min": e.llamadas_min, "max": e.llamadas_max},
                "tokens": {"min": e.tokens_min, "max": e.tokens_max},
                "spentToday": {"calls": e.gastado_hoy[0], "tokens": e.gastado_hoy[1]},
                "leftToday": {"calls": e.queda_hoy[0], "tokens": e.queda_hoy[1]},
                "withHistory": e.con_historial,
                "canScan": e.puede_escanear,
            },
            # Medida B (Fase 3): qué fuentes no se consultarán y por qué.
            "omittedSources": fuentes_omitidas(request.profile, [f.id for f in SOURCES]),
        }

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
        # Sin confirmar la estimación de Gemini no se escanea (Fase 1, B4): lo
        # impone el motor, no solo la interfaz.
        rechazo = _usar_confirmacion(ctx, request.confirmation, perfil)
        if rechazo is not None:
            raise HTTPException(status_code=409, detail={"code": rechazo,
                                                         "detail": _MENSAJES_CONFIRMACION[rechazo]})
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
            # Medida B (Fase 3): lo que no encaja con el tema no se consulta y se dice.
            omitidas = fuentes_omitidas(perfil, [f.id for f in activas])
            activas = [f for f in activas if f.id not in omitidas]
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
                            should_stop=lambda: scan_id in ctx.cancelled_runs, omitidas=omitidas)
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
                            resumen = await asyncio.to_thread(
                                functools.partial(_juzgar, ctx, run_id, resultado, tema=perfil.keywords,
                                                  descripcion=perfil.topic or perfil.name))
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
            while True:
                try:
                    evento = await asyncio.wait_for(cola.get(), timeout=KEEPALIVE_S)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if evento is None:
                    break
                yield _sse(evento)

        return StreamingResponse(emitir(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    return rutas
