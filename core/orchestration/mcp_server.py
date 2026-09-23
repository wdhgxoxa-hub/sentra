"""
Servidor MCP del Radar (`reddit-intel-agent-mcp`)
=================================================

Expone el radar como herramientas Model Context Protocol sobre stdio, de modo
que cualquier cliente de IA (Claude Desktop, Cursor, etc.) pueda invocarlo:

- `scan_subreddit(subreddit, limit, sort)`  — escanea, filtra, analiza e indexa.
- `search_pain_points(query, min_score, limit)` — búsqueda híbrida RRF.
- `get_opportunity_details(opportunity_id)` — ficha completa con síntesis JTBD.

La lógica vive en `build_tools`, que devuelve funciones planas. El registro en
el servidor es una capa fina por encima: así las herramientas se pueden probar
sin levantar un transporte stdio.

Ejecución:

    python -m core.orchestration.mcp_server
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .graph import RadarDependencies
from .pipeline import RadarPipeline, create_default_dependencies
from .state import MIN_SIGNAL_SCORE

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

SERVER_NAME = "reddit-intel-agent-mcp"


def build_tools(
    deps: RadarDependencies,
    gate_min_score: float = MIN_SIGNAL_SCORE,
) -> dict[str, Callable[..., Any]]:
    """
    Construye las tres herramientas del radar sobre unas dependencias dadas.

    Devuelve funciones planas, no objetos del SDK, para que sean invocables y
    verificables sin transporte de por medio.

    `gate_min_score` es el corte de CUALIFICACION de cada señal suelta que
    aplica el grafo al escanear (MIN_SIGNAL_SCORE); el de las oportunidades
    consolidadas lo pone el propio pipeline (MIN_OPPORTUNITY_SCORE). No confundirlo con el `min_score` de `search_pain_points`,
    que filtra lo YA almacenado en una consulta.
    """
    pipeline = RadarPipeline(deps=deps, min_score=gate_min_score)

    def scan_subreddit(
        subreddit: str,
        limit: int = 25,
        sort: str = "hot",
    ) -> dict[str, Any]:
        """
        Escanea un subreddit de extremo a extremo: ingesta, filtrado de dolor,
        análisis JTBD con scoring temporal, persistencia vectorial y corte de
        calidad.

        Devuelve las oportunidades cualificadas, las estadísticas de la pasada
        y los errores no fatales que se hayan producido.
        """
        return pipeline.run(subreddit=subreddit, limit=limit, sort=sort)

    def search_pain_points(
        query: str,
        min_score: float = 0.0,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Busca puntos de dolor ya indexados combinando similitud semántica
        densa y coincidencia léxica BM25 mediante fusión recíproca de rangos.

        `min_score` filtra por puntuación de oportunidad en la escala 0-100.
        """
        filter_sql = (
            f"opportunity_score >= {float(min_score)}" if min_score else None
        )
        try:
            results = deps.get_search_engine().search(
                query, limit=limit, filter_sql=filter_sql
            )
        # Frontera con el cliente MCP: LanceDB y el embedder pueden fallar de
        # muchas formas; la herramienta responde vacio y lo deja en el log.
        except Exception as exc:  # noqa: BLE001 - frontera con el cliente MCP
            logger.error("search_pain_points: %s", exc)
            return []

        return [result.model_dump() for result in results]

    def get_opportunity_details(opportunity_id: str) -> dict[str, Any] | None:
        """
        Recupera la ficha completa de una oportunidad por su identificador,
        con su síntesis Jobs-To-Be-Done.

        Devuelve `None` si el identificador no existe.
        """
        try:
            record = deps.store.get_by_id(opportunity_id)
        # Frontera con el cliente MCP (misma razon que search_pain_points).
        except Exception as exc:  # noqa: BLE001 - frontera con el cliente MCP
            logger.error("get_opportunity_details(%s): %s", opportunity_id, exc)
            return None

        if not record:
            return None

        # El vector son cientos de flotantes sin valor para un cliente de IA.
        return {k: v for k, v in record.items() if k not in ("vector", "_distance")}

    return {
        "scan_subreddit": scan_subreddit,
        "search_pain_points": search_pain_points,
        "get_opportunity_details": get_opportunity_details,
    }


def create_server(
    deps: RadarDependencies | None = None,
    gate_min_score: float = MIN_SIGNAL_SCORE,
) -> FastMCP:
    """Crea el servidor MCP con las tres herramientas registradas."""
    from mcp.server.fastmcp import FastMCP

    deps = deps or create_default_dependencies()
    server = FastMCP(SERVER_NAME)

    for name, fn in build_tools(deps, gate_min_score=gate_min_score).items():
        server.add_tool(fn, name=name)

    return server


def main() -> None:
    """Punto de entrada del servidor sobre stdio."""
    logging.basicConfig(level=logging.INFO)
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
