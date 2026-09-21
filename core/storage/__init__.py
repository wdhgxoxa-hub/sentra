"""
Capa de Almacenamiento y Recuperación (Fase 4)
==============================================

Superficie pública del módulo de persistencia del Reddit Intelligence Radar:

- `LanceDBStore`: almacén columnar embebido sobre Apache Lance.
- `OpportunityRecord`: modelo canónico de una oportunidad persistida.
- `HybridSearchEngine`: fusión RRF de recuperación densa y léxica BM25.
- `HybridSearchResult`: resultado unificado con el desglose de la fusión.
- `get_embedder`: selector de proveedor de embeddings (semántico por defecto).
- `FastEmbedEmbedder` / `HashEmbedder`: proveedor real y degradado explícito.
- `resolve_db_path`: resolución configurable de la ruta del almacén.

Uso típico:

    from core.storage import LanceDBStore, HybridSearchEngine, OpportunityRecord

    store = LanceDBStore()                      # embeddings semánticos reales
    store.insert_opportunities([OpportunityRecord(id="t3_abc", text="...")])

    engine = HybridSearchEngine(store=store)
    engine.index_corpus(corpus)
    resultados = engine.search("no puedo exportar facturas", limit=10)
"""

from .embeddings import (
    DEFAULT_MODEL_NAME,
    DEFAULT_VECTOR_DIM,
    HASH_FALLBACK_DIM,
    EmbeddingError,
    FastEmbedEmbedder,
    HashEmbedder,
    TextEmbedder,
    get_embedder,
)
from .hybrid_search import HybridSearchEngine, HybridSearchResult
from .lancedb_store import (
    DB_PATH_ENV_VAR,
    PROJECT_ROOT,
    DefaultTextEmbedder,
    LanceDBStore,
    OpportunityRecord,
    resolve_db_path,
)

__all__ = [
    # Persistencia
    "LanceDBStore",
    "OpportunityRecord",
    "resolve_db_path",
    "DB_PATH_ENV_VAR",
    "PROJECT_ROOT",
    # Recuperación
    "HybridSearchEngine",
    "HybridSearchResult",
    # Embeddings
    "get_embedder",
    "TextEmbedder",
    "FastEmbedEmbedder",
    "HashEmbedder",
    "EmbeddingError",
    "DEFAULT_MODEL_NAME",
    "DEFAULT_VECTOR_DIM",
    "HASH_FALLBACK_DIM",
    # Alias histórico (deprecado): usar HashEmbedder
    "DefaultTextEmbedder",
]
