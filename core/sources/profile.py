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
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from core.evidence.model import SearchQuery

from .phrases import (
    INTENTS,
    PHRASE_LIBRARY_VERSION,
    Intent,
    idioma_de_frase,
    phrases_for,
)
from .sitios_stackexchange import SITIOS, sitio_de

#: Ventana por defecto: la compuerta G6 mira los últimos 180 días.
DEFAULT_WINDOW_DAYS = 365


class ScanProfile(BaseModel):
    name: str
    #: El tema tal como lo escribió la persona (Fase 3): lo recibe el etiquetador.
    topic: str = Field(default="", max_length=200)
    #: Tipo de tema (Fase 3, medida B), de la propuesta de Gemini; None = no se sabe
    #: (sin Gemini o antiguo) y entonces no se omite ninguna fuente.
    topic_kind: Literal["software", "otro"] | None = None
    keywords: list[str] = Field(default_factory=list)
    #: El idioma de cada palabra según el asistente (la fila donde la puso la
    #: persona). Sin él, se adivina con `idioma_de`.
    keyword_languages: dict[str, Literal["es", "en"]] = Field(default_factory=dict)
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
        ajenas = set(self.keyword_languages) - set(self.keywords)
        if ajenas:
            raise ValueError(f"idioma de palabras que no están en el perfil: {sorted(ajenas)}")
        desconocidos = {sitio_de(o) for o in self.targets.get("stackexchange", [])} - set(SITIOS)
        if desconocidos:
            raise ValueError(f"sitios de Stack Exchange fuera del catálogo: {sorted(desconocidos)}")
        return self

    def to_query(self, now: datetime | None = None) -> SearchQuery:
        ahora = now or datetime.now(UTC)
        return SearchQuery(
            keywords=self.keywords,
            keyword_languages=dict(self.keyword_languages),
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


#: Palabras del tema demasiado genéricas para decir, solas, que un texto es del tema.
_GENERICAS = frozenset({"small", "business", "businesses", "software", "tool", "tools", "online",
                        "service", "services", "company", "companies", "best", "free", "negocio",
                        "negocios", "pequenos", "pequenas", "empresa", "empresas", "para"})
#: Una mención cuenta si está en el arranque del texto; más adelante hacen falta dos.
_ARRANQUE = 300
_RAIZ = 6


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn").casefold()


def menciona_el_tema(texto: str, query: SearchQuery) -> bool:
    """Si un texto habla del tema del perfil: raíces de sus palabras distintivas
    (sin tildes, 6 letras) en el arranque del texto, o al menos dos veces.
    Algolia devolvía comentarios de HN que solo compartían una palabra suelta."""
    raices = {_sin_tildes(p)[:_RAIZ] for palabra in query.keywords
              for p in re.findall(r"\w+", palabra) if len(p) >= 4 and _sin_tildes(p) not in _GENERICAS}
    if not raices:
        return True
    limpio = _sin_tildes(texto)

    def menciones(t: str) -> int:
        return sum(1 for p in re.findall(r"\w+", t) if any(p.startswith(r) for r in raices))

    return menciones(limpio[:_ARRANQUE]) > 0 or menciones(limpio) >= 2


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
        idioma = {p: query.keyword_languages.get(p) or idioma_de(p) for p in query.keywords}
        pares = [(palabra, frase) for frase in query.phrases for palabra in query.keywords
                 if idioma_de_frase(frase) in (None, idioma[palabra])]
        emparejadas = {p for p, _ in pares}
        pares += [(p, None) for p in query.keywords if p not in emparejadas]
    return pares[:limit]
