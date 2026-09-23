"""Gemini: traducción de citas, clave y plan de arquitectura."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .context import SidecarContext, gemini_credenciales, gemini_summary, update_dotenv
from .schemas import ArchitectRequest, GeminiRequest, ProbeResponse, TranslateRequest

logger = logging.getLogger(__name__)


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    @rutas.post("/api/translate")
    def translate_quotes(request: TranslateRequest) -> dict[str, Any]:
        """
        Traduce citas al idioma de la interfaz.

        Con clave de Gemini traduce el modelo; sin ella responde el motor sin
        conexión. Nunca devuelve error por esto: la vista tiene que poder
        pintar algo siempre, y una cita sin traducir se lee, un hueco no.
        """
        from core.intelligence import translator

        key, _modelo_guardado = gemini_credenciales(ctx)
        traducciones = translator.translate(
            request.texts,
            request.target,
            api_key=key,
            # Traducir no necesita el razonamiento del Pro y se pide a menudo:
            # el modelo rápido cuesta menos y responde antes.
            model=translator.MODELO_POR_DEFECTO,
        )
        return {"translations": [t.to_dict() for t in traducciones]}

    @rutas.post("/api/gemini")
    def save_gemini(request: GeminiRequest) -> dict[str, Any]:
        """Guarda la clave en el `.env` del proyecto."""
        if not request.apiKey.strip():
            raise HTTPException(status_code=400, detail="La clave no puede estar vacia")

        update_dotenv(
            {
                "RIR_GEMINI_API_KEY": request.apiKey.strip(),
                "RIR_GEMINI_MODEL": request.model.strip(),
            },
            ctx.env_path,
        )
        logger.info("Clave de Gemini guardada (modelo %s)", request.model)
        return {"gemini": gemini_summary(ctx)}

    @rutas.post("/api/gemini/test", response_model=ProbeResponse)
    def test_gemini() -> ProbeResponse:
        from core.intelligence import gemini_architect

        key, model = gemini_credenciales(ctx)
        ok, detalle = gemini_architect.probe_api_key(key, model=model)
        return ProbeResponse(ok=ok, detail=detalle)

    @rutas.post("/api/architect/generate")
    def architect_generate(request: ArchitectRequest) -> StreamingResponse:
        """
        Pide el plan de arquitectura y lo va sirviendo según llega.

        Se responde por trozos y no de una vez: con un modelo de razonamiento
        el documento tarda, y quien mira una pantalla quieta da la aplicación
        por colgada.
        """
        from core.intelligence import gemini_architect
        from core.intelligence.gemini_client import GeminiError, sanitize

        key, model = gemini_credenciales(ctx)
        if not key:
            raise HTTPException(
                status_code=412,
                detail="No hay clave de Gemini guardada. Se configura en Ajustes.",
            )

        def evento(datos: dict[str, Any]) -> str:
            return json.dumps(datos, ensure_ascii=False) + "\n"

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
                    yield evento({"type": "chunk", "text": trozo})
            except GeminiError as exc:
                # Ya saneado en la frontera y sin la excepción del SDK
                # encadenada: la traza no aportaría nada y podría filtrar.
                logger.warning("Fallo generando la arquitectura (%s): %s", exc.code, exc)
                yield evento({"type": "error", "code": exc.code, "detail": str(exc),
                              "missing": exc.missing})
                return
            except Exception as exc:
                logger.exception("Fallo generando la arquitectura")
                yield evento({"type": "error", "code": "internal_error",
                              "detail": sanitize(str(exc), key), "missing": []})
                return
            yield evento({"type": "done"})

        return StreamingResponse(cuerpo(), media_type="application/x-ndjson")

    return rutas
