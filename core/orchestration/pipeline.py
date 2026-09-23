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
from collections.abc import AsyncIterator, Callable, Coroutine, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast

from core.storage import LanceDBStore

from .graph import (
    DEFAULT_MAX_CYCLES,
    RadarDependencies,
    build_graph,
)
from .state import MIN_OPPORTUNITY_SCORE, MIN_SIGNAL_SCORE, RadarState, new_state

logger = logging.getLogger(__name__)


def _run_coroutine(coro: Coroutine[Any, Any, Any]) -> Any:
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
        max_age_days: int | None = None,
        timeframe: str = "month",
        env_path: str | None = None,
        client_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        self._client = client
        # Un cliente inyectado es de quien lo inyecta: invalidar no lo toca.
        self._client_inyectado = client is not None
        self.max_age_days = max_age_days
        self.timeframe = timeframe
        self.env_path = env_path
        self._client_factory = client_factory

    def invalidate(self) -> None:
        """
        Olvida el cliente construido.

        El siguiente escaneo lo rehace leyendo el `.env` de nuevo: es lo que
        hace que unas credenciales recién guardadas surtan efecto sin
        reiniciar el sidecar.
        """
        if not self._client_inyectado:
            self._client = None

    def _get_client(self) -> Any:
        if self._client is None:
            from core.ingestion import RedditIngestionClient
            from core.ingestion.auth import load_reddit_oauth

            # Sin credenciales `oauth` es None y el cliente falla con
            # RedditCredentialsMissing antes de salir a la red (AUD-003).
            oauth = load_reddit_oauth(self.env_path)
            factory = self._client_factory or (
                lambda credenciales: RedditIngestionClient(oauth=credenciales)
            )
            self._client = factory(oauth)
        return self._client

    def __call__(
        self,
        subreddit: str,
        limit: int = 25,
        sort: str = "hot",
        cursor: str | None = None,
    ) -> tuple[Sequence[dict[str, Any]], str | None]:
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

    def fetch_comments(self, subreddit: str, post_id: str) -> list[dict[str, Any]]:
        """Comentarios de un post por la API OAuth, con los límites de D-I.

        El id lleva el prefijo `t1_` de Reddit: los de posts y comentarios
        son espacios distintos y, sin prefijo, podrían coincidir.
        """
        client = self._get_client()
        comentarios = _run_coroutine(client.fetch_thread_comments(subreddit, post_id))
        return [
            {
                **comentario.model_dump(),
                "id": f"t1_{comentario.id}",
                "kind": "comment",
                "subreddit": subreddit,
            }
            for comentario in comentarios
        ]


def create_default_dependencies(
    db_path: str | None = None,
    allow_hash_fallback: bool = False,
    env_path: str | None = None,
) -> RadarDependencies:
    """Ensambla las dependencias de producción: ingesta real y almacén real."""
    return RadarDependencies(
        fetcher=RedditFetcher(env_path=env_path),
        store=LanceDBStore(db_path=db_path, allow_hash_fallback=allow_hash_fallback),
    )


def _como_estado(valores: Any) -> RadarState:
    """
    Lo que devuelve el grafo, como el estado que es.

    LangGraph tipa el resultado de `invoke`, `ainvoke` y del modo `values`
    de `astream` como un diccionario genérico, pero es el estado del
    esquema con el que se compiló el grafo: `StateGraph(RadarState)` en
    `build_graph`. Aquí, en la frontera con la librería, se dice una vez.
    """
    return cast(RadarState, valores)


class RadarPipeline:
    """
    Punto de entrada único para ejecutar el radar de extremo a extremo.

        pipeline = RadarPipeline()
        resultado = pipeline.run("smallbusiness", limit=25)
    """

    def __init__(
        self,
        deps: RadarDependencies | None = None,
        max_cycles: int = DEFAULT_MAX_CYCLES,
        min_score: float = MIN_SIGNAL_SCORE,
        cluster_threshold: float = MIN_OPPORTUNITY_SCORE,
    ) -> None:
        """
        Args:
            min_score: corte de la señal INDIVIDUAL (feed de cualificadas).
            cluster_threshold: corte del problema CONSOLIDADO (oportunidad).
        """
        self.deps = deps or create_default_dependencies()
        self.max_cycles = max_cycles
        self.min_score = min_score
        self.cluster_threshold = cluster_threshold
        self._graph = build_graph(
            self.deps,
            max_cycles=max_cycles,
            min_score=min_score,
            cluster_threshold=cluster_threshold,
        )

    def run_state(
        self,
        subreddit: str,
        limit: int = 25,
        sort: str = "hot",
    ) -> RadarState:
        """
        Ejecuta el grafo y devuelve el estado final COMPLETO.

        Lo necesita quien va a persistir: `summarize` se queda con lo que
        interesa a quien consulta, pero descarta `signals` y
        `filtered_items`, que son justo lo que hay que escribir en la base.
        """
        return _como_estado(
            self._graph.invoke(new_state(subreddit=subreddit, limit=limit, sort=sort))
        )

    async def arun_state(
        self,
        subreddit: str,
        limit: int = 25,
        sort: str = "hot",
    ) -> RadarState:
        """Gemelo asíncrono de `run_state`."""
        return _como_estado(
            await self._graph.ainvoke(new_state(subreddit=subreddit, limit=limit, sort=sort))
        )

    async def astream_state(
        self,
        subreddit: str,
        limit: int = 25,
        sort: str = "hot",
    ) -> AsyncIterator[tuple[str, Any]]:
        """
        Ejecuta el grafo emitiendo el avance nodo a nodo.

        Es lo que permite pintar una barra de progreso sin sondear: un
        escaneo puede durar minutos y preguntar "¿ya?" cada segundo es ruido
        para todas las capas.

        Emite tuplas:

            ("node",  {"node": <nombre>, "state": <estado acumulado>})
            ("final", <estado final completo>)

        Se piden los dos modos de LangGraph a la vez porque cada uno aporta
        la mitad: `updates` dice QUÉ nodo acaba de correr y `values` trae el
        estado acumulado tras ese nodo.
        """
        last_state: RadarState | None = None
        pending_node: str | None = None

        async for mode, chunk in self._graph.astream(
            new_state(subreddit=subreddit, limit=limit, sort=sort),
            stream_mode=["updates", "values"],
        ):
            if mode == "updates":
                pending_node = next(iter(chunk), None)
                continue

            last_state = _como_estado(chunk)
            if pending_node:
                yield ("node", {"node": pending_node, "state": chunk})
                pending_node = None

        yield ("final", last_state or {})

    def run(
        self,
        subreddit: str,
        limit: int = 25,
        sort: str = "hot",
    ) -> dict[str, Any]:
        """Ejecuta el grafo y devuelve el resumen para quien consulta."""
        return self.summarize(self.run_state(subreddit, limit, sort))

    async def arun(
        self,
        subreddit: str,
        limit: int = 25,
        sort: str = "hot",
    ) -> dict[str, Any]:
        """Gemelo asíncrono de `run`."""
        return self.summarize(await self.arun_state(subreddit, limit, sort))

    @staticmethod
    def summarize(final: RadarState) -> dict[str, Any]:
        """Reduce el estado final a lo que interesa a quien invoca."""
        qualified: list[dict[str, Any]] = list(final.get("qualified") or [])
        qualified.sort(key=lambda q: q.get("opportunity_score", 0.0), reverse=True)

        return {
            "subreddit": final.get("subreddit", ""),
            # Señales individuales que pasaron el filtro de higiene.
            "qualified": qualified,
            # Problemas recurrentes consolidados que superan el corte de
            # oportunidad: esto es lo que merece que alguien construya algo.
            "qualified_clusters": list(final.get("qualified_clusters") or []),
            "clusters": list(final.get("clusters") or []),
            "stored_ids": list(final.get("stored_ids") or []),
            "stats": dict(final.get("stats") or {}),
            "errors": list(final.get("errors") or []),
            "cycles": int(final.get("cycle", 0)),
        }
