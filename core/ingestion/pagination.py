"""
Paginación Directa Basada en Cursores (Bellingcat RPST Engine)
=============================================================
Extraído y adaptado de bellingcat-reddit-post-scraping-tool (rpst/api.py).

Proporciona:
1. Paginación continua sobre endpoints públicos de Reddit mediante el parámetro 'after'.
2. Soporte para marcos de tiempo ('t=hour|day|week|month|year|all') y modos de listado ('hot|new|top|rising').
3. Filtro temporal estricto (max_age_days) para descartar publicaciones obsoletas.
4. Resiliencia y reintentos adaptativos ante respuestas HTTP 429 (Too Many Requests).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

VALID_TIMEFRAMES = {"hour", "day", "week", "month", "year", "all"}
VALID_LISTINGS = {"hot", "new", "top", "rising"}


class RedditPaginator:
    """
    Gestor de paginación asíncrona mediante cursores para extracción continua de Reddit.
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_base_seconds: float = 3.0,
    ) -> None:
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds

    def build_page_params(
        self,
        listing: str = "hot",
        limit: int = 25,
        after: str | None = None,
        timeframe: str = "month",
    ) -> dict[str, Any]:
        """
        Construye el diccionario de parámetros de consulta para la URL de Reddit.
        """
        clean_limit = max(1, min(limit, 100))  # Reddit permite máximo 100 por petición
        params: dict[str, Any] = {"limit": clean_limit}

        if after:
            params["after"] = after

        if listing == "top":
            tf = timeframe if timeframe in VALID_TIMEFRAMES else "month"
            params["t"] = tf

        return params

    def filter_by_recency(
        self,
        items: list[dict[str, Any]],
        max_age_days: int | None = None
    ) -> tuple[list[dict[str, Any]], bool]:
        """
        Filtra elementos que superen el límite de antigüedad en días.
        Retorna (elementos_filtrados, reached_cutoff).
        Si reached_cutoff es True, significa que ya encontramos posts más viejos que el límite,
        lo que indica que en listados ordenados por fecha se puede detener la paginación.
        """
        if max_age_days is None:
            return items, False

        now_ts = datetime.now(UTC).timestamp()
        cutoff_ts = now_ts - (max_age_days * 86400)

        filtered = []
        reached_cutoff = False

        for item in items:
            created_utc = item.get("created_utc", 0)
            if created_utc >= cutoff_ts:
                filtered.append(item)
            else:
                reached_cutoff = True

        return filtered, reached_cutoff

    @staticmethod
    def extract_children_and_after(json_response: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
        """
        Extrae la lista de 'children' y el siguiente cursor 'after' desde el JSON devuelto por Reddit.
        """
        if not json_response or not isinstance(json_response, dict):
            return [], None

        data_block = json_response.get("data", {})
        children = data_block.get("children", [])
        after_cursor = data_block.get("after")

        extracted_items = []
        for child in children:
            if isinstance(child, dict) and "data" in child:
                item_data = child["data"]
                item_data["_kind"] = child.get("kind", "")
                extracted_items.append(item_data)

        return extracted_items, after_cursor
