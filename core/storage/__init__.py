"""
Capa de Almacenamiento y Recuperación (Fase 4)
==============================================

Superficie pública del módulo de persistencia del Reddit Intelligence Radar:

- `LanceDBStore`: almacén columnar embebido sobre Apache Lance.
- `OpportunityRecord`: modelo canónico de una oportunidad persistida.
- `get_embedder`: selector de proveedor de embeddings (semántico por defecto).
- `FastEmbedEmbedder` / `HashEmbedder`: proveedor real y degradado explícito.
- `resolve_db_path`: resolución configurable de la ruta del almacén.

La búsqueda sobre la evidencia multifuente vive en `core.evidence.search`
(D-C4); la búsqueda híbrida sobre las señales antiguas se retiró en C2.
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
from .lancedb_store import (
    DB_PATH_ENV_VAR,
    PROJECT_ROOT,
    DefaultTextEmbedder,
    LanceDBStore,
    OpportunityRecord,
    resolve_db_path,
)

__all__ = [
    "DB_PATH_ENV_VAR",
    "DEFAULT_MODEL_NAME",
    "DEFAULT_VECTOR_DIM",
    "HASH_FALLBACK_DIM",
    "PROJECT_ROOT",
    "DefaultTextEmbedder",  # alias histórico (deprecado): usar HashEmbedder
    "EmbeddingError",
    "FastEmbedEmbedder",
    "HashEmbedder",
    "LanceDBStore",
    "OpportunityRecord",
    "TextEmbedder",
    "get_embedder",
    "resolve_db_path",
]
