"""
Presupuesto de una fuente por escaneo (F2.1, D-M4)
==================================================

Se comprueba ANTES de cada petición y de cada ítem: agotado, no sale nada
más. Lo que ya salió se cobra, reintentos incluidos (también gastan cuota).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import SourceBudgetExhausted

#: Por fuente y por escaneo (D-M4).
DEFAULT_MAX_REQUESTS = 25
DEFAULT_MAX_ITEMS = 500


@dataclass
class CupoDelEscaneo:
    """Piezas que caben en un escaneo, compartidas por todas sus fuentes (Fase 3).

    Ninguna fuente se lleva más de la mitad; lo que no usan las fuentes sin
    resultados queda para las que sí traen, dentro de su mitad. En el escaneo 1
    de la Fase 3, YouTube trajo 500 de 512 piezas y el resto de fuentes casi
    nada: el juez vio un escaneo de YouTube.
    """

    total: int
    gastado: int = 0

    @property
    def por_fuente(self) -> int:
        return self.total // 2


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
    #: El cupo compartido del escaneo en curso (lo pone run_multisource_scan).
    cupo: CupoDelEscaneo | None = field(default=None, repr=False)

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
        if self.spent_items >= self.max_items:
            self._agotado(f"{self.spent_items} de {self.max_items} ítems")
        if self.cupo is not None:
            if self.spent_items >= self.cupo.por_fuente:
                self._agotado(f"la mitad del cupo del escaneo ({self.cupo.por_fuente} ítems)")
            if self.cupo.gastado >= self.cupo.total:
                self._agotado(f"cupo del escaneo lleno ({self.cupo.total} ítems)")
            self.cupo.gastado += 1
        self.spent_items += 1

    def _agotado(self, detalle: str) -> None:
        raise SourceBudgetExhausted(self.source or "fuente", f"presupuesto agotado: {detalle}")
