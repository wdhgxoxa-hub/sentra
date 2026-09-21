"""
Runner de Alto Nivel del Radar
==============================

Envuelve el grafo compilado en una interfaz cómoda, síncrona y asíncrona, y
proporciona el adaptador que conecta el cliente real de ingesta con la firma
de fetcher que espera el grafo.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Awaitable, Dict, List, Optional, Sequence, Tuple

from core.storage import LanceDBStore

from .graph import (
    DEFAULT_MAX_CYCLES,
    DEFAULT_TARGET_QUALIFIED,
    RadarDependencies,
    build_graph,
)
from .state import MIN_OPPORTUNITY_SCORE, RadarState, new_state

logger = logging.getLogger(__name__)


def _run_coroutine(coro: Awaitable[Any]) -> Any:
    """
    Ejecuta una corrutina desde código síncrono, haya o no un bucle activo.

    Si ya se está dentro de un bucle (por ejemplo, el servidor MCP atendiendo
    una petición), `asyncio.run` lanzaría `RuntimeError`, así que se delega en
    un hilo con su propio bucle.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class RedditFetcher:
    """
    Adaptador entre `RedditIngestionClient` y la firma de fetcher del grafo.

    Traduce en ambos sentidos el cursor de paginación: entrega a Reddit el
    `after` con el que el grafo quiere reanudar y devuelve el cursor de la
    página siguiente, de modo que cada vuelta del ciclo avanza de verdad en
    lugar de releer la primera página.
    """

    def __init__(
        self,
        client: Any = None,
        max_age_days: Optional[int] = None,
        timeframe: str = "month",
    ) -> None:
        self._client = client
        self.max_age_days = max_age_days
        self.timeframe = timeframe

    def _get_client(self) -> Any:
        if self._client is None:
            from core.ingestion import RedditIngestionClient

            self._client = RedditIngestionClient()
        return self._client

    def __call__(
        self,
        subreddit: str,
        limit: int = 25,
        sort: str = "hot",
        cursor: Optional[str] = None,
    ) -> Tuple[Sequence[Dict[str, Any]], Optional[str]]:
        client = self._get_client()
        posts, next_cursor = _run_coroutine(
            client.fetch_subreddit_page(
                subreddit=subreddit,
                listing=sort,
                limit=limit,
                after=cursor,
                timeframe=self.timeframe,
                max_age_days=self.max_age_days,
            )
        )
        items = [post.model_dump() for post in posts]
        return items, next_cursor


def create_default_dependencies(
    db_path: Optional[str] = None,
    allow_hash_fallback: bool = False,
) -> RadarDependencies:
    """Ensambla las dependencias de producción: ingesta real y almacén real."""
    return RadarDependencies(
        fetcher=RedditFetcher(),
        store=LanceDBStore(db_path=db_path, allow_hash_fallback=allow_hash_fallback),
    )


class RadarPipeline:
    """
    Punto de entrada único para ejecutar el radar de extremo a extremo.

        pipeline = RadarPipeline()
        resultado = pipeline.run("smallbusiness", limit=25)
    """

    def __init__(
        self,
        deps: Optional[RadarDependencies] = None,
        target_qualified: int = DEFAULT_TARGET_QUALIFIED,
        max_cycles: int = DEFAULT_MAX_CYCLES,
        min_score: float = MIN_OPPORTUNITY_SCORE,
    ) -> None:
        self.deps = deps or create_default_dependencies()
        self.target_qualified = target_qualified
        self.max_cycles = max_cycles
        self.min_score = min_score
        self._graph = build_graph(
            self.deps,
            target_qualified=target_qualified,
            max_cycles=max_cycles,
            min_score=min_score,
        )

    def run(
        self,
        subreddit: str,
        limit: int = 25,
        sort: str = "hot",
    ) -> Dict[str, Any]:
        """Ejecuta el grafo y devuelve el estado final."""
        final: RadarState = self._graph.invoke(
            new_state(subreddit=subreddit, limit=limit, sort=sort)
        )
        return self._summarize(final)

    async def arun(
        self,
        subreddit: str,
        limit: int = 25,
        sort: str = "hot",
    ) -> Dict[str, Any]:
        """Gemelo asíncrono de `run`."""
        final: RadarState = await self._graph.ainvoke(
            new_state(subreddit=subreddit, limit=limit, sort=sort)
        )
        return self._summarize(final)

    @staticmethod
    def _summarize(final: RadarState) -> Dict[str, Any]:
        """Reduce el estado final a lo que interesa a quien invoca."""
        qualified: List[Dict[str, Any]] = list(final.get("qualified") or [])
        qualified.sort(key=lambda q: q.get("opportunity_score", 0.0), reverse=True)

        return {
            "subreddit": final.get("subreddit", ""),
            "qualified": qualified,
            "stored_ids": list(final.get("stored_ids") or []),
            "stats": dict(final.get("stats") or {}),
            "errors": list(final.get("errors") or []),
            "cycles": int(final.get("cycle", 0)),
        }
