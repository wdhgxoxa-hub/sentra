"""
Motor de Búsqueda Híbrida (Dense Vectorial + BM25 Léxico con RRF)
=================================================================
Extraído y adaptado de vectfox-hybrid-search (core/agentic-retrieval.js).

Proporciona:
1. Fusión de Recuperación Recíproca (Reciprocal Rank Fusion - RRF).
2. Combinación equilibrada de:
   - Similitud semántica densa (LanceDB vector K-NN).
   - Coincidencia léxica exacta ponderada por BM25 (rank_bm25).
3. Resolución de casos donde la búsqueda semántica falla ante nombres propios de librerías,
   errores técnicos específicos o herramientas de nicho (ej: 'pgpool', 'FastAPI 404', 'Stripe VAT').
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple
from pydantic import BaseModel, Field
from rank_bm25 import BM25Okapi

from .lancedb_store import LanceDBStore

logger = logging.getLogger(__name__)


class HybridSearchResult(BaseModel):
    """Resultado unificado de búsqueda híbrida con desglose RRF."""
    id: str
    text: str
    subreddit: str = ""
    author: str = ""
    score: int = 0
    opportunity_score: float = 0.0
    urgency_tier: str = "LOW"
    job_statement: str = ""
    current_solution: Optional[str] = None
    rrf_score: float
    dense_rank: Optional[int] = None
    bm25_rank: Optional[int] = None
    bm25_score: Optional[float] = None


class HybridSearchEngine:
    """
    Motor de búsqueda híbrida que integra LanceDB con el algoritmo BM25Okapi mediante RRF.
    """

    def __init__(
        self,
        store: LanceDBStore,
        rrf_k: int = 60,
        dense_weight: float = 0.6,
        bm25_weight: float = 0.4
    ) -> None:
        self.store = store
        self.rrf_k = rrf_k
        self.dense_weight = dense_weight
        self.bm25_weight = bm25_weight

        self._bm25_index: Optional[BM25Okapi] = None
        self._corpus_docs: List[Dict[str, Any]] = []
        self._corpus_id_map: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Tokenizador léxico limpio para BM25."""
        if not text:
            return []
        cleaned = re.sub(r"[^\w\s-]", " ", text.lower())
        tokens = [t.strip() for t in cleaned.split() if len(t.strip()) > 1]
        return tokens

    def index_corpus(self, documents: Sequence[Dict[str, Any]]) -> int:
        """
        Construye o actualiza el índice BM25Okapi a partir del corpus de documentos.
        Cada documento debe contener al menos 'id' y 'text'.
        """
        if not documents:
            self._bm25_index = None
            self._corpus_docs = []
            self._corpus_id_map = {}
            return 0

        self._corpus_docs = list(documents)
        self._corpus_id_map = {str(d["id"]): d for d in self._corpus_docs}

        tokenized_corpus = [
            self._tokenize(
                f"{d.get('text', '')} {d.get('job_statement', '')} {d.get('current_solution', '')}"
            )
            for d in self._corpus_docs
        ]

        self._bm25_index = BM25Okapi(tokenized_corpus)
        return len(self._corpus_docs)

    def extend_corpus(self, documents: Sequence[Dict[str, Any]]) -> int:
        """
        Añade documentos al índice léxico conservando los ya indexados.

        `index_corpus` reemplaza el corpus entero, lo que en una ejecución por
        lotes sucesivos haría desaparecer de la rama BM25 todo lo cosechado
        antes. Los documentos con un `id` ya presente se sustituyen.
        """
        if not documents:
            return len(self._corpus_docs)

        merged: Dict[str, Dict[str, Any]] = {
            str(doc["id"]): doc for doc in self._corpus_docs
        }
        for doc in documents:
            merged[str(doc["id"])] = doc

        return self.index_corpus(list(merged.values()))

    def search(
        self,
        query: str,
        limit: int = 10,
        filter_sql: Optional[str] = None
    ) -> List[HybridSearchResult]:
        """
        Ejecuta la búsqueda híbrida combinada:
        1. Consulta densa en LanceDB.
        2. Consulta léxica en BM25Okapi.
        3. Fusión recíproca de rangos (RRF).
        """
        if not query.strip():
            return []

        # Candidate pool size (el doble del límite solicitado para mejor intersección)
        candidate_k = max(limit * 3, 20)

        # 1. Búsqueda Densa en LanceDB
        dense_results = self.store.search_text(
            query_text=query,
            limit=candidate_k,
            filter_sql=filter_sql
        )

        dense_ranks: Dict[str, int] = {}
        for rank, item in enumerate(dense_results, 1):
            dense_ranks[str(item["id"])] = rank

        # 2. Búsqueda Léxica en BM25
        bm25_ranks: Dict[str, int] = {}
        bm25_scores: Dict[str, float] = {}

        if self._bm25_index and self._corpus_docs:
            query_tokens = self._tokenize(query)
            if query_tokens:
                doc_scores = self._bm25_index.get_scores(query_tokens)
                # Ordenar por puntuación BM25 descendente
                scored_indices = [
                    (idx, float(score))
                    for idx, score in enumerate(doc_scores)
                    if score > 0.0
                ]
                scored_indices.sort(key=lambda x: x[1], reverse=True)
                candidates = scored_indices[:candidate_k]

                # El predicado SQL lo aplica LanceDB, es decir, solo la rama
                # densa. Sin este paso la rama léxica reintroduciría documentos
                # que el filtro ya había descartado. Se restringe el conjunto
                # ya acotado de candidatos, no la tabla entera.
                if filter_sql and candidates:
                    allowed = self.store.filter_ids(
                        [str(self._corpus_docs[idx]["id"]) for idx, _ in candidates],
                        filter_sql,
                    )
                    candidates = [
                        (idx, score)
                        for idx, score in candidates
                        if str(self._corpus_docs[idx]["id"]) in allowed
                    ]

                for rank, (idx, score) in enumerate(candidates, 1):
                    doc_id = str(self._corpus_docs[idx]["id"])
                    bm25_ranks[doc_id] = rank
                    bm25_scores[doc_id] = round(score, 4)

        # 3. Reciprocal Rank Fusion (RRF)
        all_candidate_ids = set(dense_ranks.keys()).union(set(bm25_ranks.keys()))
        if not all_candidate_ids:
            return []

        rrf_fused: List[Tuple[str, float]] = []
        for doc_id in all_candidate_ids:
            score = 0.0
            if doc_id in dense_ranks:
                score += self.dense_weight / (self.rrf_k + dense_ranks[doc_id])
            if doc_id in bm25_ranks:
                score += self.bm25_weight / (self.rrf_k + bm25_ranks[doc_id])
            rrf_fused.append((doc_id, score))

        # Ordenar por puntaje RRF descendente
        rrf_fused.sort(key=lambda x: x[1], reverse=True)

        results: List[HybridSearchResult] = []
        for doc_id, rrf_score in rrf_fused[:limit]:
            # Recuperar metadatos del documento (de LanceDB o del corpus map)
            doc_data = None
            if doc_id in self._corpus_id_map:
                doc_data = self._corpus_id_map[doc_id]
            else:
                doc_data = self.store.get_by_id(doc_id)

            if not doc_data:
                continue

            results.append(
                HybridSearchResult(
                    id=doc_id,
                    text=doc_data.get("text", ""),
                    subreddit=doc_data.get("subreddit", ""),
                    author=doc_data.get("author", "[deleted]"),
                    score=int(doc_data.get("score", 0)),
                    opportunity_score=float(doc_data.get("opportunity_score", 0.0)),
                    urgency_tier=doc_data.get("urgency_tier", "LOW"),
                    job_statement=doc_data.get("job_statement", ""),
                    current_solution=doc_data.get("current_solution"),
                    rrf_score=round(rrf_score, 6),
                    dense_rank=dense_ranks.get(doc_id),
                    bm25_rank=bm25_ranks.get(doc_id),
                    bm25_score=bm25_scores.get(doc_id)
                )
            )

        return results
