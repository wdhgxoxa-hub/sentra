"""
Esquema común de evidencia (F2.2)
=================================

Toda fuente, con su API y sus nombres propios, entrega `EvidenceItem`. Lo
que el juez cuenta (fuentes, autores, hilos, fechas) sale de aquí, así que
aquí se hace cumplir lo que no puede fallar: id global con su fuente,
fechas en UTC, URL al original, autor solo como hash y procedencia.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

#: Qué es cada pieza de evidencia en su plataforma.
EvidenceKind = Literal[
    "post", "comment", "question", "answer", "issue", "discussion", "review", "product",
]

#: `real`: vino de la API de una plataforma. `demo`: corpus inventado.
DataSource = Literal["real", "demo"]

_HASH = re.compile(r"^[0-9a-f]{64}$")


def content_fingerprint(text: str) -> str:
    """Huella del contenido: igual para el mismo texto con otras mayúsculas o espacios.

    Es la clave de la caché de etiquetas (el mismo texto nunca se etiqueta
    dos veces, F3) y la primera señal de crossposting (F2.6).
    """
    return hashlib.sha256(" ".join(text.casefold().split()).encode("utf-8")).hexdigest()


class Engagement(BaseModel):
    """Interacción normalizada. None = la plataforma no la informa (no es 0)."""

    score: int | None = None
    replies: int | None = None
    reactions: int | None = None
    views: int | None = None


class EvidenceItem(BaseModel):
    """Una pieza de evidencia de cualquier fuente."""

    id: str
    source: str
    community: str
    kind: EvidenceKind
    title: str | None = None
    text: str
    url: str
    author_hash: str | None
    created_at: datetime
    fetched_at: datetime
    language: str | None = None
    thread_id: str | None = None
    engagement: Engagement = Field(default_factory=Engagement)
    native_metrics: dict[str, Any] = Field(default_factory=dict)
    data_source: DataSource
    run_id: str | None = None

    @field_validator("text")
    @classmethod
    def _texto_no_vacio(cls, texto: str) -> str:
        if not texto.strip():
            raise ValueError("la evidencia no puede tener el texto vacío")
        return texto

    @field_validator("url")
    @classmethod
    def _url_al_original(cls, url: str) -> str:
        # Atribución con enlace al original (R5): solo https, nada de
        # javascript:, data: ni rutas relativas que la interfaz abriría.
        if not url.startswith("https://"):
            raise ValueError("la URL al original debe ser https")
        return url

    @field_validator("author_hash")
    @classmethod
    def _solo_hash(cls, valor: str | None) -> str | None:
        # R9: el nombre de usuario no se guarda nunca, ni por descuido.
        if valor is not None and not _HASH.match(valor):
            raise ValueError("el autor solo se guarda como hash salado")
        return valor

    @field_validator("created_at", "fetched_at")
    @classmethod
    def _en_utc(cls, fecha: datetime) -> datetime:
        if fecha.tzinfo is None:
            raise ValueError("fecha sin zona horaria: no se puede saber qué instante es")
        return fecha.astimezone(UTC)

    @model_validator(mode="after")
    def _id_global(self) -> EvidenceItem:
        prefijo = f"{self.source}:"
        if not self.id.startswith(prefijo) or len(self.id) == len(prefijo):
            raise ValueError(f"el id global debe ser '{prefijo}<id nativo>'")
        return self


class SearchQuery(BaseModel):
    """Lo que un perfil de escaneo pide a cada fuente (F2.5).

    `targets` mapea cada fuente a sus objetivos (subreddits, sitios y tags,
    repos, foros, instancias...). Sin palabras clave es modo descubrimiento,
    y hay que pedirlo explícitamente.
    """

    keywords: list[str] = Field(default_factory=list)
    phrases: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=lambda: ["en", "es"])
    targets: dict[str, list[str]] = Field(default_factory=dict)
    since: datetime | None = None
    discovery: bool = False

    @field_validator("keywords", "phrases")
    @classmethod
    def _limpios(cls, terminos: list[str]) -> list[str]:
        return [t.strip() for t in terminos if t.strip()]

    @model_validator(mode="after")
    def _tema_o_descubrimiento(self) -> SearchQuery:
        if not self.keywords and not self.discovery:
            raise ValueError("sin palabras clave hay que activar el modo descubrimiento")
        if self.discovery and not self.phrases:
            raise ValueError("el modo descubrimiento necesita frases de intención")
        return self
