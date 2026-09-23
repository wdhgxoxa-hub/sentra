"""Cliente HTTP de las fuentes: un solo punto de creación (los tests lo sustituyen)."""

from __future__ import annotations

import httpx


def new_client() -> httpx.AsyncClient:
    """Cliente para hablar con las APIs de las fuentes."""
    return httpx.AsyncClient(follow_redirects=False)
