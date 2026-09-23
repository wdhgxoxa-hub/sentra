"""Búsqueda híbrida (densa + BM25 con fusión RRF): `/api/search`."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from .context import SidecarContext
from .schemas import SearchRequest, SearchResponse

logger = logging.getLogger(__name__)


def hit_to_camel(hit: Any) -> dict[str, Any]:
    """Adapta un resultado de búsqueda al contrato de `ui/src/types/radar.ts`."""
    return {
        "id": hit.id,
        "text": hit.text,
        "subreddit": hit.subreddit,
        "opportunityScore": hit.opportunity_score,
        "urgencyTier": hit.urgency_tier,
        "jobStatement": hit.job_statement,
        "currentSolution": hit.current_solution,
        "rrfScore": hit.rrf_score,
        "denseRank": hit.dense_rank,
        "bm25Rank": hit.bm25_rank,
        "bm25Score": hit.bm25_score,
        "dataSource": hit.data_source,
    }


def router(ctx: SidecarContext) -> APIRouter:
    rutas = APIRouter()

    @rutas.post("/api/search", response_model=SearchResponse)
    def search(request: SearchRequest) -> SearchResponse:
        filter_sql = (
            f"opportunity_score >= {float(request.min_score)}"
            if request.min_score
            else None
        )
        try:
            results = ctx.deps.get_search_engine().search(
                request.query, limit=request.limit, filter_sql=filter_sql
            )
        except Exception as exc:
            logger.exception("Fallo en la busqueda hibrida")
            raise HTTPException(status_code=500, detail=f"Fallo de busqueda: {exc}")

        return SearchResponse(
            query=request.query,
            hits=[hit_to_camel(hit) for hit in results],
        )

    return rutas
