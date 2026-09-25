"""Dossier y plan de construcción de un veredicto (Fase E): `/api/documents/{kind}`.

Carga el veredicto con toda su evidencia, pide el texto al modelo de
documentos (D-C1), lo compone y lo pinta en PDF o Markdown. Lo generado se
guarda por (veredicto, documento, idioma, modelo, forzado) en memoria y en
disco antes de responder (core/documents/almacen.py): exportar otra vez, en
otro formato o tras cerrar la app, no vuelve a llamar al modelo. El plan de un nicho
que no es CONSTRUIR se rechaza antes de gastar ninguna llamada, salvo que se
fuerce (y entonces lleva la franja).
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from core.documents.almacen import AlmacenDeDocumentos
from core.documents.compose import PlanNotRecommended, compose_dossier, compose_plan
from core.documents.generate import generate_document
from core.documents.model import DocumentModel
from core.documents.pdf_report import render_pdf
from core.llm.base import JsonGenerator, LLMBudgetExhausted, LLMError

from .context import SidecarContext

Kind = Literal["dossier", "plan"]
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


class DocumentRequest(BaseModel):
    verdictId: str
    format: Literal["pdf", "md"]
    language: Literal["es", "en"] = "es"
    force: bool = False


def _disponible(ctx: SidecarContext) -> bool:
    """Los documentos leen el veredicto de PostgreSQL: sin persistencia, no hay."""
    return ctx.persist_default


def _cargar(ctx: SidecarContext, verdict_id: str) -> dict[str, Any] | None:
    """El veredicto con toda su evidencia. En un hilo: psycopg no funciona sobre
    el ProactorEventLoop de Windows."""
    from core.judge.store import verdict_detail
    from core.storage.postgres_store import (
        PostgresStore,
        resolver_dsn,
        run_async,
    )

    dsn = resolver_dsn(ctx.postgres_dsn)

    async def leer() -> dict[str, Any] | None:
        async with PostgresStore(dsn=dsn) as store:
            return await verdict_detail(store, verdict_id)

    return run_async(leer())


def _proveedor(ctx: SidecarContext) -> tuple[JsonGenerator, str]:
    """El proveedor con el modelo de documentos (D-C1: el guardado en Ajustes o,
    sin guardado, el Pro 3.x más reciente)."""
    from core.llm.gemini import GeminiProvider

    # Un documento no es de ningún escaneo: su uso va sin ejecución y solo le
    # aplica el tope diario.
    clave, modelo = ctx.resolver_modelo("documentos")
    return GeminiProvider(clave, control=ctx.control()), modelo


def nombre_de_archivo(documento: DocumentModel, formato: str) -> str:
    """«SENTRA - <título>.<ext>» sin caracteres que Windows no admite."""
    limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", documento.title)
    limpio = " ".join(limpio.split())[:90].rstrip()
    return f"SENTRA - {limpio}.{formato}"


def _documento(ctx: SidecarContext, kind: Kind, peticion: DocumentRequest
               ) -> tuple[DocumentModel, int]:
    """(documento compuesto, llamadas al modelo en esta petición)."""
    detalle = _cargar(ctx, peticion.verdictId)
    if detalle is None:
        raise HTTPException(status_code=404, detail={
            "code": "verdict_not_found", "detail": f"No hay ningún veredicto {peticion.verdictId}."})
    if kind == "plan" and detalle["verdict"] != "CONSTRUIR" and not peticion.force:
        raise HTTPException(status_code=409, detail={
            "code": PlanNotRecommended.code,
            "detail": f"El juez dice {detalle['verdict']} ({detalle['rule']})."})
    almacen = AlmacenDeDocumentos(ctx.carpeta_documentos) if ctx.carpeta_documentos else None
    # Lo ya guardado se reutiliza ANTES de resolver el modelo (Fase 2): listar
    # modelos puede llamar a Google y un documento guardado no lo necesita.
    guardado = next((d for (v, k, idioma, _m, forzado), d in ctx.documentos.items()
                     if (v, k, idioma, forzado) == (peticion.verdictId, kind, peticion.language, peticion.force)),
                    None)
    if guardado is None and almacen is not None:
        guardado = almacen.buscar(peticion.verdictId, kind, peticion.language, peticion.force)
    if guardado is not None:
        return guardado, 0
    try:
        proveedor, modelo = _proveedor(ctx)
    except LLMError as exc:
        estado = 412 if exc.code == "gemini_not_configured" else 502
        raise HTTPException(status_code=estado, detail={"code": exc.code, "detail": str(exc)}) from None

    clave = (peticion.verdictId, kind, peticion.language, modelo, peticion.force)
    try:
        generado = generate_document(proveedor, modelo, kind, detalle, peticion.language)
    except LLMBudgetExhausted as exc:
        # Un tope de Gemini: el código dice cuál, y su texto dónde subirlo.
        raise HTTPException(status_code=429, detail={"code": exc.motivo, "detail": str(exc)}) from None
    except LLMError as exc:
        raise HTTPException(status_code=502, detail={"code": exc.code, "detail": str(exc)}) from None
    ahora = datetime.now(UTC)
    if kind == "dossier":
        documento = compose_dossier(detalle, generado.content, peticion.language, model=modelo,
                                    generated_at=ahora)
    else:
        documento = compose_plan(detalle, generado.content, peticion.language, model=modelo,
                                 generated_at=ahora, forced=peticion.force)
    # En disco antes de responder, que es antes de que Rust abra el diálogo de
    # guardar: cancelarlo o cerrar la app ya no pierde lo que costó la llamada.
    if almacen is not None:
        almacen.guardar(clave, documento)
    ctx.documentos[clave] = documento
    return documento, generado.calls


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    @rutas.get("/api/documents/status")
    async def document_status(verdictId: str) -> dict[str, Any]:
        """Si el dossier y el plan de un veredicto ya están guardados, por
        idioma: se abren sin gastar. No llama a nadie."""
        if not _UUID.fullmatch(verdictId):
            raise HTTPException(status_code=400, detail={
                "code": "invalid_verdict_id", "detail": "El identificador del veredicto no es válido."})
        guardados: set[tuple[str, str]] = set()
        if ctx.carpeta_documentos:
            almacen = AlmacenDeDocumentos(ctx.carpeta_documentos)
            guardados = await asyncio.to_thread(almacen.estado, verdictId)
        guardados |= {(k, idioma) for (v, k, idioma, _m, _f) in ctx.documentos if v == verdictId}
        return {"verdictId": verdictId,
                **{k: {idioma: (k, idioma) in guardados for idioma in ("es", "en")} for k in ("dossier", "plan")}}

    @rutas.post("/api/documents/{kind}")
    async def document(kind: Kind, peticion: DocumentRequest) -> Response:
        if not _disponible(ctx):
            raise HTTPException(status_code=503, detail={
                "code": "documents_unavailable",
                "detail": "Los documentos necesitan PostgreSQL y un escaneo juzgado."})
        documento, llamadas = await asyncio.to_thread(_documento, ctx, kind, peticion)
        if peticion.format == "pdf":
            cuerpo: bytes = await asyncio.to_thread(render_pdf, documento)
            tipo = "application/pdf"
        else:
            cuerpo = documento.to_markdown().encode("utf-8")
            tipo = "text/markdown; charset=utf-8"
        return Response(content=cuerpo, media_type=tipo, headers={
            "X-Sentra-Llm-Calls": str(llamadas),
            "X-Sentra-File-Name": quote(nombre_de_archivo(documento, peticion.format)),
        })

    return rutas
