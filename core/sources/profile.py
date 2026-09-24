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

import re
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field, field_validator, model_validator

from core.evidence.model import SearchQuery

from .phrases import (
    INTENTS,
    PHRASE_LIBRARY_VERSION,
    Intent,
    idioma_de_frase,
    phrases_for,
)

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


#: Señales de español en una palabra del tema: tildes y eñes, o palabras frecuentes.
_TILDES = re.compile(r"[áéíóúüñ¿¡]")
_ES = frozenset({"de", "para", "y", "la", "el", "los", "las", "con", "por", "una", "un", "del", "sin",
                 "factura", "facturas", "facturacion", "autonomos", "pymes", "negocio", "negocios",
                 "cobrar", "cliente", "clientes", "empresa", "empresas"})


def idioma_de(texto: str) -> str:
    """«es» o «en» para una palabra del tema (heurística: tildes o palabras frecuentes)."""
    minusculas = texto.casefold()
    if _TILDES.search(minusculas) or set(re.findall(r"[a-z]+", minusculas)) & _ES:
        return "es"
    return "en"


def term_pairs(query: SearchQuery, limit: int, *,
               solo_tema: bool = False) -> list[tuple[str | None, str | None]]:
    """(palabra clave, frase) a buscar, repartidas antes de repetir.

    Con el presupuesto de una fuente no caben todas las combinaciones: se
    recorre cada frase con todas las palabras antes de pasar a la siguiente,
    para que ninguna palabra se quede sin buscar. Una palabra solo se une a
    frases de su idioma: «facturación autónomos is there a tool» no encontraba
    nada en ninguna fuente; una palabra sin frases de su idioma se busca sola.
    En descubrimiento, solo frases (palabra None); con tema y sin frases, o con
    `solo_tema` (fuentes que exigen todas las palabras, como Bluesky y
    Mastodon), solo palabras: el juez filtra el dolor después.
    """
    pares: list[tuple[str | None, str | None]]
    if query.discovery:
        pares = [(None, frase) for frase in query.phrases]
    elif solo_tema or not query.phrases:
        pares = [(palabra, None) for palabra in query.keywords]
    else:
        pares = [(palabra, frase) for frase in query.phrases for palabra in query.keywords
                 if idioma_de_frase(frase) in (None, idioma_de(palabra))]
        emparejadas = {p for p, _ in pares}
        pares += [(p, None) for p in query.keywords if p not in emparejadas]
    return pares[:limit]
