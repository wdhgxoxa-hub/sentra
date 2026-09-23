"""
Perfil de escaneo (F2.5)
========================

Sustituye al «escaneo por subreddit»: tema (palabras clave del dominio),
intenciones de dolor de la biblioteca versionada, idiomas y objetivos por
fuente (subreddits, sitios y tags de Stack Exchange, repos de GitHub,
foros Discourse, instancias Mastodon, búsquedas de YouTube...). Sin tema,
el modo descubrimiento busca solo por intención, para encontrar nichos no
previstos.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field, field_validator, model_validator

from core.evidence.model import SearchQuery

from .phrases import INTENTS, PHRASE_LIBRARY_VERSION, Intent, phrases_for

#: Ventana por defecto: la compuerta G6 mira los últimos 180 días.
DEFAULT_WINDOW_DAYS = 365


class ScanProfile(BaseModel):
    name: str
    keywords: list[str] = Field(default_factory=list)
    intents: list[Intent] = Field(default_factory=lambda: list(INTENTS))
    languages: list[str] = Field(default_factory=lambda: ["en", "es"])
    targets: dict[str, list[str]] = Field(default_factory=dict)
    window_days: int = Field(default=DEFAULT_WINDOW_DAYS, ge=1, le=3650)
    discovery: bool = False
    phrase_library_version: str = PHRASE_LIBRARY_VERSION

    @field_validator("keywords")
    @classmethod
    def _limpias(cls, palabras: list[str]) -> list[str]:
        return [p.strip() for p in palabras if p.strip()]

    @model_validator(mode="after")
    def _tema_o_descubrimiento(self) -> ScanProfile:
        if self.discovery and self.keywords:
            raise ValueError("el modo descubrimiento no lleva tema: busca solo por intención")
        if not self.discovery and not self.keywords:
            raise ValueError("un perfil necesita tema o el modo descubrimiento")
        if not self.intents:
            raise ValueError("hace falta al menos una intención de dolor")
        return self

    def to_query(self, now: datetime | None = None) -> SearchQuery:
        ahora = now or datetime.now(UTC)
        return SearchQuery(
            keywords=self.keywords,
            phrases=phrases_for(self.intents, self.languages),
            languages=self.languages,
            targets=self.targets,
            since=ahora - timedelta(days=self.window_days),
            discovery=self.discovery,
        )


def term_pairs(query: SearchQuery, limit: int) -> list[tuple[str | None, str | None]]:
    """(palabra clave, frase) a buscar, repartidas antes de repetir.

    Con el presupuesto de una fuente no caben todas las combinaciones: se
    recorre cada frase con todas las palabras antes de pasar a la siguiente,
    para que ninguna palabra se quede sin buscar. En descubrimiento, solo
    frases (palabra None); con tema y sin frases, solo palabras.
    """
    pares: list[tuple[str | None, str | None]]
    if query.discovery:
        pares = [(None, frase) for frase in query.phrases]
    elif not query.phrases:
        pares = [(palabra, None) for palabra in query.keywords]
    else:
        pares = [(palabra, frase) for frase in query.phrases for palabra in query.keywords]
    return pares[:limit]
