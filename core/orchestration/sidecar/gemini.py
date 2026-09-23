"""Gemini: traducción de citas, clave, modelos y plan de arquitectura."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from core.envfile import update_dotenv
from core.llm.base import LLMError
from core.llm.gemini import UsoDeModelo, elegir_modelo, sanitize

from .context import SidecarContext, gemini_credenciales, gemini_summary
from .schemas import (
    ArchitectRequest,
    GeminiModel,
    GeminiModelsResponse,
    GeminiRequest,
    ProbeResponse,
    TranslateRequest,
)

logger = logging.getLogger(__name__)


def _evento(datos: dict[str, Any]) -> str:
    """Una línea del NDJSON del plan (AUD-020)."""
    return json.dumps(datos, ensure_ascii=False) + "\n"


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

    @rutas.post("/api/translate")
    def translate_quotes(request: TranslateRequest) -> dict[str, Any]:
        """
        Traduce citas al idioma de la interfaz.

        Con clave de Gemini traduce el modelo general; sin ella, o si el
        modelo no está disponible, responde el motor sin conexión. Nunca
        devuelve error por esto: la vista tiene que poder pintar algo siempre,
        y una cita sin traducir se lee, un hueco no.
        """
        from core.intelligence import translator

        # Traducir no necesita el razonamiento del Pro y se pide a menudo.
        try:
            key, modelo = ctx.resolver_modelo("defecto")
        except LLMError as exc:
            logger.info("Traducción sin conexión (%s)", exc.code)
            key, modelo = "", ""
        traducciones = translator.translate(
            request.texts, request.target, api_key=key, model=modelo
        )
        return {"translations": [t.to_dict() for t in traducciones]}

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

    @rutas.post("/api/architect/generate")
    def architect_generate(request: ArchitectRequest) -> StreamingResponse:
        """
        Pide el plan de arquitectura y lo va sirviendo según llega.

        Se responde por trozos y no de una vez: con un modelo de razonamiento
        el documento tarda, y quien mira una pantalla quieta da la aplicación
        por colgada.
        """
        from core.intelligence import gemini_architect

        if not gemini_credenciales(ctx).key:
            raise HTTPException(
                status_code=412,
                detail="No hay clave de Gemini guardada. Se configura en Ajustes.",
            )
        try:
            key, model = ctx.resolver_modelo("documentos")
        except LLMError as exc:
            # Modelo guardado desaparecido, sin candidato o API caída: error
            # tipado en el formato del plan, sin llegar a llamar al modelo.
            fallo = {"type": "error", "code": exc.code, "detail": str(exc), "missing": []}
            return StreamingResponse(iter([_evento(fallo)]), media_type="application/x-ndjson")

        def cuerpo() -> Iterator[str]:
            # Una línea JSON por evento (AUD-020): `chunk` con texto, y al
            # final `done` o `error`. El fallo llega a mitad del texto ya
            # enviado y no se puede cambiar el código de estado; antes se
            # escribía dentro del documento, que así se daba por terminado.
            try:
                for trozo in gemini_architect.stream_architecture(
                    request.cluster,
                    api_key=key,
                    model=model,
                    language=request.language,
                ):
                    yield _evento({"type": "chunk", "text": trozo})
            except LLMError as exc:
                # Ya saneado en la frontera y sin la excepción del SDK
                # encadenada: la traza no aportaría nada y podría filtrar.
                logger.warning("Fallo generando la arquitectura (%s): %s", exc.code, exc)
                yield _evento({"type": "error", "code": exc.code, "detail": str(exc),
                               "missing": exc.missing})
                return
            except Exception as exc:
                logger.exception("Fallo generando la arquitectura")
                yield _evento({"type": "error", "code": "internal_error",
                               "detail": sanitize(str(exc), key), "missing": []})
                return
            yield _evento({"type": "done"})

        return StreamingResponse(cuerpo(), media_type="application/x-ndjson")

    return rutas
