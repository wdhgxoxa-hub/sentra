"""
Contratos HTTP del sidecar
==========================

Peticiones y respuestas de todos los routers. Viven juntos porque son el
contrato con el puente de Rust: se revisan de una vez.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ScanRequest(BaseModel):
    subreddit: str
    limit: int = Field(default=25, ge=1, le=100)
    sort: str = Field(default="hot")
    persist: bool | None = None
    # Quien invoca puede fijar el identificador. Sin eso no hay forma de
    # cancelar un escaneo que todavia no ha empezado a responder.
    runId: str | None = None

    @field_validator("subreddit")
    @classmethod
    def _subreddit_not_blank(cls, value: str) -> str:
        cleaned = (value or "").strip().removeprefix("r/").removeprefix("/")
        if not cleaned:
            raise ValueError("El subreddit no puede estar vacio")
        return cleaned


class SearchRequest(BaseModel):
    query: str
    min_score: float = Field(default=0.0, alias="minScore", ge=0.0, le=100.0)
    limit: int = Field(default=10, ge=1, le=100)

    model_config = {"populate_by_name": True}

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("La consulta no puede estar vacia")
        return value


class ModeRequest(BaseModel):
    mode: Literal["synthetic", "reddit"]


class CredentialsRequest(BaseModel):
    clientId: str
    clientSecret: str
    # Obligatorio y sin valor por defecto: se valida al guardar (AUD-014).
    userAgent: str = ""
    username: str | None = None
    password: str | None = None

    @field_validator("clientId", "clientSecret")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("No puede estar vacio")
        return value.strip()


class BlueprintRequest(BaseModel):
    """Peticion de especificacion de proyecto.

    El cluster viaja entero en el cuerpo en lugar de por clave: quien lo pide
    (el puente de Rust) ya lo ha leido de PostgreSQL, y volver a consultarlo
    aqui abriria una segunda fuente de verdad que podria discrepar.
    """

    cluster: dict[str, Any] = Field(default_factory=dict)
    language: str = "es"
    # Plan de Gemini de la sesión, si lo hay: la sección 7 del documento lo
    # incluye igual que el PDF (D-H).
    architecture: str | None = None


class GeminiRequest(BaseModel):
    """Clave y modelos de Gemini. Un modelo vacío significa «automático»."""

    apiKey: str = ""
    model: str = ""
    generalModel: str = ""


class GeminiModel(BaseModel):
    id: str
    displayName: str


class GeminiModelsResponse(BaseModel):
    """Modelos que la clave puede usar y los que se usarían ahora mismo."""

    ok: bool
    code: str | None = None
    detail: str = ""
    models: list[GeminiModel] = Field(default_factory=list)
    general: str | None = None
    documents: str | None = None


class ArchitectRequest(BaseModel):
    """Peticion de arquitectura para un cluster.

    Igual que el blueprint, el cluster viaja entero: quien lo pide ya lo leyo
    de PostgreSQL.
    """

    cluster: dict[str, Any] = Field(default_factory=dict)
    language: str = "es"


class DocumentRequest(BaseModel):
    """Peticion del documento en PDF (AUD-008).

    El cluster llega entero, igual que para el blueprint. `architecture` es
    el Markdown del plan de Gemini si se genero en la sesion; si no, el
    documento lo declara «No generado».
    """

    cluster: dict[str, Any] = Field(default_factory=dict)
    language: str = "es"
    architecture: str | None = None


class TranslateRequest(BaseModel):
    """Tanda de citas a traducir.

    El limite esta para que una vista con muchas citas no dispare una peticion
    enorme al modelo por accidente.
    """

    texts: list[str] = Field(default_factory=list, max_length=60)
    target: str = "es"


class ProbeResponse(BaseModel):
    ok: bool
    detail: str


class CancelRequest(BaseModel):
    runId: str


class CancelResponse(BaseModel):
    runId: str
    # False si no habia ningun escaneo con ese id en marcha. No es un error:
    # puede ser una cancelacion anticipada, o llegar tarde.
    wasActive: bool


class ScanResponse(BaseModel):
    subreddit: str
    runId: str | None = None
    cycles: int = 0
    stats: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    qualified: list[dict[str, Any]] = Field(default_factory=list)
    clusters: list[dict[str, Any]] = Field(default_factory=list)
    qualifiedClusters: list[dict[str, Any]] = Field(default_factory=list)
    persisted: bool = False
    # Por que no se persistio. Tragarse el motivo convertia un fallo de base
    # de datos en un silencioso "persisted: false" imposible de diagnosticar.
    persistError: str | None = None
    # "completed" o "failed". Un escaneo sin acceso a la fuente es "failed"
    # con un codigo estable que la interfaz traduce (AUD-003).
    status: str = "completed"
    failureCode: str | None = None
    retryAfterSeconds: int | None = None
    # "demo" o "reddit", y el resultado Top N de la ejecucion (AUD-007).
    dataSource: str = "demo"
    top: dict[str, Any] | None = None


class SearchResponse(BaseModel):
    query: str
    hits: list[dict[str, Any]] = Field(default_factory=list)
