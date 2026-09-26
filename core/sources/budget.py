"""
Presupuesto de una fuente por escaneo (F2.1, D-M4)
==================================================

Se comprueba ANTES de cada petición y de cada ítem: agotado, no sale nada
más. Lo que ya salió se cobra, reintentos incluidos (también gastan cuota).
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from core.evidence.model import EvidenceItem, SearchQuery
from core.judge.quality import MIN_CHARS, MIN_WORDS

from .errors import SourceBudgetExhausted
from .profile import menciona_el_tema

#: Por fuente y por escaneo (D-M4).
DEFAULT_MAX_REQUESTS = 25
DEFAULT_MAX_ITEMS = 500


@dataclass
class CupoDelEscaneo:
    """Piezas ÚTILES que caben en un escaneo, compartidas por todas sus fuentes (Fase 3).

    Ninguna fuente se lleva más de la mitad; lo que no usan las fuentes sin
    resultados queda para las que sí traen, dentro de su mitad. En el escaneo 1
    de la Fase 3, YouTube trajo 500 de 512 piezas y el resto de fuentes casi
    nada: el juez vio un escaneo de YouTube.

    Walter (escaneo 2): el cupo cuenta piezas útiles, no traídas, y Bluesky no
    puede meter duplicados (83 de sus 250). Útil = no repite el id ni el texto
    de otra del escaneo (huella sin enlaces, cifras ni signos), tiene el largo
    mínimo del filtro de calidad y nombra el tema. Lo que no es útil se guarda
    igual, pero no gasta cupo. Traer tiene su propio tope (`bruto_max`).
    """

    total: int
    #: Piezas útiles contadas en el escaneo.
    gastado: int = 0
    #: Piezas traídas en el escaneo, útiles o no.
    brutas: int = 0
    utiles: Counter[str] = field(default_factory=Counter)
    _huellas: set[str] = field(default_factory=set, repr=False)
    _ids: set[str] = field(default_factory=set, repr=False)

    @property
    def por_fuente(self) -> int:
        return self.total // 2

    @property
    def bruto_max(self) -> int:
        """Traer sin fin tampoco: vectorizar y guardar lo traído cuesta tiempo."""
        return 2 * self.total

    def registrar(self, item: EvidenceItem, query: SearchQuery) -> bool:
        """Cuenta la pieza; True si es útil (y entonces gasta cupo de su fuente)."""
        self.brutas += 1
        huella = huella_de_cupo(f"{item.title or ''} {item.text}")
        repetida = item.id in self._ids or huella in self._huellas
        self._ids.add(item.id)
        self._huellas.add(huella)
        texto = item.text.strip()
        util = (not repetida and len(texto) >= MIN_CHARS and len(texto.split()) >= MIN_WORDS
                and menciona_el_tema(f"{item.title or ''} {item.text}", query))
        if util:
            self.gastado += 1
            self.utiles[item.source] += 1
        return util

    def motivo_global(self) -> str | None:
        """Por qué ninguna fuente puede traer más; None si se puede."""
        if self.gastado >= self.total:
            return f"cupo del escaneo lleno ({self.total} piezas útiles)"
        if self.brutas >= self.bruto_max:
            return f"tope de piezas traídas del escaneo ({self.bruto_max})"
        return None

    def motivo_para_parar(self, fuente: str) -> str | None:
        """Por qué `fuente` no puede traer más; None si puede."""
        if self.utiles[fuente] >= self.por_fuente:
            return f"la mitad del cupo del escaneo ({self.por_fuente} piezas útiles)"
        return self.motivo_global()


def huella_de_cupo(texto: str) -> str:
    """El texto sin enlaces, cifras, signos, tildes ni mayúsculas: dos piezas que
    solo cambian en eso son la misma para el cupo. Medido en el escaneo 2: atrapa
    al traerlas 70 de los 90 duplicados (los 20 exactos y 50 de los 70 casi
    iguales); el resto lo sigue quitando la deduplicación final por vectores."""
    plano = unicodedata.normalize("NFKD", _ENLACE.sub(" ", texto)).casefold()
    sin_tildes = "".join(c for c in plano if not unicodedata.combining(c))
    return " ".join(_NO_LETRA.sub(" ", sin_tildes).split())


_ENLACE = re.compile(r"(?:https?://|www\.)\S+")
_NO_LETRA = re.compile(r"[^a-zñ]+")


@dataclass
class SourceBudget:
    """Topes de una fuente en un escaneo. None = sin tope de ese tipo.

    `max_units` son unidades de cuota de la plataforma (YouTube cobra 100
    por búsqueda y 1 por lectura); `max_usd`, dinero (X cobra por recurso).
    """

    source: str = ""
    max_requests: int = DEFAULT_MAX_REQUESTS
    max_items: int = DEFAULT_MAX_ITEMS
    max_units: float | None = None
    max_usd: float | None = None
    spent_requests: int = 0
    spent_items: int = 0
    spent_units: float = 0.0
    spent_usd: float = 0.0

    def charge_request(self, units: float = 0.0, usd: float = 0.0) -> None:
        """Cobra una petición antes de enviarla; si no cabe, no sale."""
        if self.spent_requests >= self.max_requests:
            self._agotado(f"{self.spent_requests} de {self.max_requests} peticiones")
        if self.max_units is not None and self.spent_units + units > self.max_units:
            self._agotado(f"{self.spent_units:g} + {units:g} de {self.max_units:g} unidades")
        if self.max_usd is not None and self.spent_usd + usd > self.max_usd:
            self._agotado(f"{self.spent_usd:.4f} + {usd:.4f} de {self.max_usd:.4f} USD")
        self.spent_requests += 1
        self.spent_units += units
        self.spent_usd += usd

    def charge_item(self) -> None:
        """Tope de piezas traídas de la fuente. El cupo del escaneo (piezas útiles) lo
        lleva el bucle del escaneo, que ve cada pieza: `CupoDelEscaneo`."""
        if self.spent_items >= self.max_items:
            self._agotado(f"{self.spent_items} de {self.max_items} ítems")
        self.spent_items += 1

    def _agotado(self, detalle: str) -> None:
        raise SourceBudgetExhausted(self.source or "fuente", f"presupuesto agotado: {detalle}")
