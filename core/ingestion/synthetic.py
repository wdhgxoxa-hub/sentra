"""
Fuente Sintética (Modo Simulación)
==================================

Corpus de posts fabricados que sustituye a Reddit como fuente de datos,
manteniendo intacto todo lo demás: el grafo, el análisis, el clustering,
LanceDB y PostgreSQL son los reales.

Existe por dos motivos:

1. **Reddit está cerrado** (deuda D8): el acceso anónimo devuelve 403 y el
   registro de aplicaciones OAuth está bloqueado a nivel de cuenta.
2. **Una demo necesita datos estables.** Enseñar el producto con una fuente
   que cambia cada minuto hace imposible explicar por qué un problema
   cualifica y otro no.

El corpus está construido para que el clustering tenga trabajo de verdad:

    A. Exportación manual de facturas   5 comunidades, disposición a pagar
    B. Conciliación bancaria a mano     3 comunidades
    C. Soporte repetitivo               3 comunidades
    D. Despliegues lentos               1 comunidad  (no debe cualificar)
    E. Ruido y spam de afiliado         descartado por el filtro o vetado

Se sirve en dos páginas encadenadas por cursor, igual que haría Reddit, para
que el grafo dé dos vueltas y el ciclo se vea en la interfaz.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger(__name__)

# Fecha en el futuro: fuerza recencia máxima, como si fuesen de hoy. Usar
# "ahora" haría que el corpus envejeciera y las puntuaciones de la demo
# cambiasen solas con el paso de las semanas.
RECENT_UTC = 4102444800.0

# --- A: exportación de facturas (el problema fuerte) ---
INVOICES = (
    "The invoice export is completely broken and it is frustrating. "
    "I would pay for a tool that fixes this manual invoice process."
)
INVOICES_MILD = "This manual invoice export is broken and wastes hours every week."

# --- B: conciliación bancaria ---
BANK = (
    "Reconciling the bank statement by hand is a tedious process. "
    "I would pay for something that automates this manual matching."
)

# --- C: soporte repetitivo ---
SUPPORT = (
    "Answering the same support questions is a repetitive task that "
    "takes hours every day. I need automation for this manual work."
)

# --- D: despliegues (una sola comunidad: no debe cualificar) ---
DEPLOY = "The release step takes forever to finish and kills my productivity."

PAGE_ONE: list[tuple[str, str, str, str]] = [
    ("t3_inv01", "smallbusiness", "Manual invoice export is broken again", INVOICES),
    ("t3_inv02", "SaaS", "Invoice export broken after the update", INVOICES),
    ("t3_inv03", "accounting", "Manual invoice workflow is broken", INVOICES_MILD),
    ("t3_bank01", "smallbusiness", "Bank reconciliation is manual and slow", BANK),
    ("t3_bank02", "bookkeeping", "Manual bank matching every month", BANK),
    ("t3_sup01", "startups", "Support replies are a repetitive task", SUPPORT),
    ("t3_noise1", "smallbusiness", "Happy friday everyone",
     "Hope you all have a great weekend."),
    ("t3_spam1", "SaaS", "This tool fixed my broken invoice problem",
     "Use my referral link and promo code SAVE20 for a discount, ref=99."),
]

PAGE_TWO: list[tuple[str, str, str, str]] = [
    ("t3_inv04", "freelance", "Manual invoice export broken once more", INVOICES),
    ("t3_inv05", "bookkeeping", "Invoice export is broken and manual", INVOICES_MILD),
    ("t3_bank03", "freelance", "Manual reconciliation wastes my week", BANK),
    ("t3_sup02", "smallbusiness", "Repetitive support work takes hours", SUPPORT),
    ("t3_sup03", "SaaS", "Manual support replies every day", SUPPORT),
    ("t3_dep01", "devops", "Deploying takes forever to finish", DEPLOY),
    ("t3_noise2", "devops", "Just saying hello to the sub", "Nice to meet you all."),
]

PAGES = [PAGE_ONE, PAGE_TWO]


def _as_item(index: int, post_id: str, subreddit: str, title: str, body: str) -> dict[str, Any]:
    return {
        "id": post_id,
        "subreddit": subreddit,
        "title": title,
        "selftext": body,
        "author": f"u/{post_id}",
        "score": 40 + index * 7,
        "num_comments": 7,
        "upvote_ratio": 0.95,
        "created_utc": RECENT_UTC,
        "url": f"https://reddit.com/r/{subreddit}/comments/{post_id}",
        "permalink": f"https://reddit.com/r/{subreddit}/comments/{post_id}",
    }


class SyntheticFetcher:
    """
    Fuente con la misma firma que `RedditFetcher`.

    Ignora el subreddit pedido a propósito: el corpus es fijo, y fingir que
    cada foro tiene contenido distinto daría una falsa sensación de realidad
    en una demo.
    """

    name = "synthetic"

    def __init__(self, pages: Sequence[Sequence[tuple]] | None = None) -> None:
        self.pages = list(pages if pages is not None else PAGES)
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        subreddit: str,
        limit: int = 25,
        sort: str = "hot",
        cursor: str | None = None,
    ) -> tuple[Sequence[dict[str, Any]], str | None]:
        self.calls.append({"subreddit": subreddit, "limit": limit, "sort": sort,
                           "cursor": cursor})

        index = 0 if cursor is None else int(cursor)
        if index >= len(self.pages):
            return [], None

        page = self.pages[index]
        next_cursor = str(index + 1) if index + 1 < len(self.pages) else None

        items = [
            _as_item(position, post_id, sub, title, body)
            for position, (post_id, sub, title, body) in enumerate(page)
        ]
        if limit:
            items = items[:limit]

        logger.info(
            "Fuente sintetica: pagina %d, %d posts (cursor siguiente: %s)",
            index + 1, len(items), next_cursor,
        )
        return items, next_cursor


def total_posts() -> int:
    """Cuántos posts contiene el corpus completo."""
    return sum(len(page) for page in PAGES)
