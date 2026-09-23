"""Documento de la oportunidad: `/api/blueprint` y `/api/document/pdf` (D-H)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from .context import SERVICE_VERSION, SidecarContext
from .schemas import BlueprintRequest, DocumentRequest


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    @rutas.post("/api/blueprint")
    def blueprint(request: BlueprintRequest) -> dict[str, Any]:
        """
        Sintetiza el PRD de un cluster.

        Las secciones y el Markdown salen del mismo `DocumentModel` que el PDF
        (D-H): lo que se ve y lo que se exporta coinciden. La síntesis es
        determinista y no toca disco ni red, así que responde en el mismo
        hilo: no hay nada que esperar.
        """
        from core.documents.model import build_document
        from core.intelligence.blueprint import build_blueprint

        modelo = build_document(request.cluster, request.language,
                                architecture=request.architecture)
        return {
            **build_blueprint(request.cluster, request.language).to_dict(),
            "sections": [seccion.to_dict() for seccion in modelo.sections],
            "markdown": modelo.to_markdown(),
        }

    @rutas.post("/api/document/pdf")
    def document_pdf(request: DocumentRequest) -> Response:
        """
        Genera el documento de la oportunidad en PDF y devuelve sus bytes.

        Rust los guarda donde elija quien exporta: el sidecar no escribe en
        disco.
        """
        from core.documents.pdf_report import build_pdf

        pdf = build_pdf(
            request.cluster,
            request.language,
            architecture=request.architecture,
            version=SERVICE_VERSION,
        )
        return Response(content=pdf, media_type="application/pdf")

    return rutas
