"""Gemini: clave y modelos. La traducción de citas y el plan de arquitectura
por cluster se retiraron con la ficha de oportunidad (C2, D-C3)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from core.envfile import update_dotenv
from core.llm.base import LLMError
from core.llm.gemini import UsoDeModelo, elegir_modelo

from .context import SidecarContext, gemini_credenciales, gemini_summary
from .schemas import GeminiModel, GeminiModelsResponse, GeminiRequest, ProbeResponse

logger = logging.getLogger(__name__)


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    def modelos(*, refrescar: bool) -> GeminiModelsResponse:
        """Modelos que la clave puede usar, y el que se usaría en cada uso."""
        credenciales = gemini_credenciales(ctx)
        if not credenciales.key:
            return GeminiModelsResponse(
                ok=False, code="gemini_not_configured", detail="No hay clave de Gemini guardada."
            )
        try:
            lista = ctx.listar_modelos(credenciales.key, refrescar=refrescar)
        except LLMError as exc:
            # Un fallo de red o de cuota no dice nada de la clave.
            causa = "No se pudo contactar con Gemini" if exc.transient else "La clave no funciona"
            return GeminiModelsResponse(ok=False, code=exc.code, detail=f"{causa}: {exc}")

        def elegido(uso: UsoDeModelo, guardado: str | None) -> str | None:
            try:
                return elegir_modelo(lista, uso, guardado=guardado).id
            except LLMError:
                return None

        return GeminiModelsResponse(
            ok=True,
            models=[GeminiModel(id=m.id, displayName=m.display_name) for m in lista],
            general=elegido("defecto", credenciales.general_model),
            documents=elegido("documentos", credenciales.documents_model),
        )

    @rutas.post("/api/gemini")
    def save_gemini(request: GeminiRequest) -> dict[str, Any]:
        """Guarda la clave y los modelos elegidos (vacío = automático) en el `.env`.

        Sin clave nueva se conserva la guardada: elegir modelo no obliga a
        volver a teclear la clave. Sin ninguna de las dos, 400.
        """
        clave = request.apiKey.strip() or gemini_credenciales(ctx).key
        if not clave:
            raise HTTPException(status_code=400, detail="La clave no puede estar vacia")

        update_dotenv(
            {
                "RIR_GEMINI_API_KEY": clave,
                "RIR_GEMINI_MODEL": request.model.strip(),
                "RIR_GEMINI_GENERAL_MODEL": request.generalModel.strip(),
            },
            ctx.env_path,
        )
        ctx.modelos_gemini.clear()  # la lista era de la clave anterior
        logger.info("Clave de Gemini guardada")
        return {"gemini": gemini_summary(ctx)}

    @rutas.get("/api/gemini/models", response_model=GeminiModelsResponse)
    def gemini_models() -> GeminiModelsResponse:
        return modelos(refrescar=False)

    @rutas.post("/api/gemini/test", response_model=ProbeResponse)
    def test_gemini() -> ProbeResponse:
        """Prueba la clave listando sus modelos: una llamada real, sin generar texto."""
        resultado = modelos(refrescar=True)
        if not resultado.ok:
            return ProbeResponse(ok=False, detail=resultado.detail)
        return ProbeResponse(ok=True, detail=(
            f"Clave válida: {len(resultado.models)} modelos disponibles. "
            f"General: {resultado.general or 'sin candidato'}; "
            f"documentos: {resultado.documents or 'sin candidato'}."
        ))

    return rutas
