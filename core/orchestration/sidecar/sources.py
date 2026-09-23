"""Fuentes: estado verificado, credenciales, prueba real, encendido y modo comercial."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.envfile import update_dotenv
from core.evidence.author import load_or_create_salt
from core.sources import http as fuentes_http
from core.sources.base import SourceAdapter
from core.sources.budget import SourceBudget
from core.sources.catalog import SOURCES, by_id
from core.sources.errors import SourceCredentialsMissing
from core.sources.registry import COMMERCIAL_MODE_ENV, credentials_for, source_status

from .context import SidecarContext, load_dotenv

#: Una prueba es una llamada mínima: con esto sobra, reintentos incluidos.
PROBE_MAX_REQUESTS = 3


class CredentialsBody(BaseModel):
    values: dict[str, str]


class EnabledBody(BaseModel):
    enabled: bool


def _camel(nombre: str) -> str:
    cabeza, *resto = nombre.split("_")
    return cabeza + "".join(p.capitalize() for p in resto)


def _en_camel(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {_camel(k): _en_camel(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_en_camel(v) for v in valor]
    return valor


def commercial_mode(env: dict[str, str]) -> bool:
    return (env.get(COMMERCIAL_MODE_ENV) or "").strip() == "1"


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    def fuente(source_id: str) -> type[SourceAdapter]:
        clase = by_id(source_id)
        if clase is None:
            raise HTTPException(status_code=404, detail=f"Fuente desconocida: {source_id}")
        return clase

    def entorno() -> dict[str, str]:
        return dict(load_dotenv(ctx.env_path, env={}))

    def estado(clase: type[SourceAdapter], env: dict[str, str]) -> dict[str, Any]:
        guardado = ctx.sources_state.get(clase.id)
        return _en_camel(source_status(clase, env, guardado, commercial_mode(env))
                         .model_dump(mode="json"))

    @rutas.get("/api/sources")
    def list_sources() -> dict[str, Any]:
        env = entorno()
        return {"commercialMode": commercial_mode(env),
                "sources": [estado(clase, env) for clase in SOURCES]}

    @rutas.post("/api/sources/{source_id}/credentials")
    def save_source_credentials(source_id: str, body: CredentialsBody) -> dict[str, Any]:
        """Guarda las credenciales en el .env (escritura atómica). Nunca se devuelven."""
        clase = fuente(source_id)
        campos = {c.name: c.env_var for c in clase.credential_fields}
        desconocidos = set(body.values) - set(campos)
        if desconocidos:
            raise HTTPException(status_code=400,
                                detail=f"Campos desconocidos: {', '.join(sorted(desconocidos))}")
        update_dotenv({campos[k]: v.strip() for k, v in body.values.items()}, ctx.env_path)
        # Con credenciales nuevas, lo verificado antes ya no vale.
        ctx.sources_state.reset(clase.id)
        return estado(clase, entorno())

    @rutas.post("/api/sources/{source_id}/probe")
    async def probe_source(source_id: str) -> dict[str, Any]:
        """Llamada mínima real a la API; el resultado queda registrado."""
        clase = fuente(source_id)
        env = entorno()
        credenciales = credentials_for(clase, env)
        faltan = [c.name for c in clase.credential_fields if c.required and c.name not in credenciales]
        if clase.requires_credentials and faltan:
            error = SourceCredentialsMissing(clase.id, f"faltan: {', '.join(faltan)}")
            return {"ok": False, "code": error.code, "detail": error.detail, "checkedAt": None}
        async with fuentes_http.new_client() as cliente:
            adaptador = clase(
                http=cliente,
                budget=SourceBudget(source=clase.id, max_requests=PROBE_MAX_REQUESTS),
                credentials=credenciales,
                author_salt=load_or_create_salt(ctx.env_path),
            )
            resultado = await adaptador.probe()
        ctx.sources_state.record_probe(clase.id, resultado)
        return _en_camel(resultado.model_dump(mode="json"))

    @rutas.post("/api/sources/{source_id}/enabled")
    def set_source_enabled(source_id: str, body: EnabledBody) -> dict[str, Any]:
        clase = fuente(source_id)
        ctx.sources_state.set_disabled(clase.id, not body.enabled)
        return estado(clase, entorno())

    @rutas.post("/api/sources/commercial-mode")
    def set_commercial_mode(body: EnabledBody) -> dict[str, Any]:
        update_dotenv({COMMERCIAL_MODE_ENV: "1" if body.enabled else "0"}, ctx.env_path)
        return list_sources()

    return rutas
