"""
Almacenamiento Columnar Serverless en Disco (LanceDB Storage Engine)
===================================================================
Extraído y adaptado de lancedb-vectordb-recipes (tutorials/Local-RAG-from-Scratch).

Proporciona:
1. Almacenamiento vectorial en disco formato columnar Apache Lance (.lance).
2. Cero servicios daemon externos (opera embebido sobre filesystem local o S3).
3. Inserción por lotes y consultas de similitud vectorial de baja latencia.
4. Filtrado híbrido por predicados SQL (ej. 'opportunity_score >= 60.0 AND urgency_tier = "HIGH"').
5. Ruta de almacenamiento configurable (argumento > RIR_LANCEDB_PATH > raíz del proyecto).
6. Literales SQL escapados en origen: los identificadores nunca se interpolan en crudo.

Los embeddings los aporta `core.storage.embeddings`, que exige un proveedor
semántico real salvo degradado explícito.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa
from pydantic import BaseModel, Field

from .embeddings import (
    DEFAULT_VECTOR_DIM,
    HashEmbedder,
    TextEmbedder,
    get_embedder,
)

logger = logging.getLogger(__name__)

# Raiz del proyecto: <raiz>/core/storage/lancedb_store.py -> parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Variable de entorno que permite reubicar el almacen sin tocar codigo.
DB_PATH_ENV_VAR = "RIR_LANCEDB_PATH"


def resolve_db_path(db_path: str | Path | None = None) -> Path:
    """
    Resuelve la ruta del almacen LanceDB en cascada:

    1. El argumento explicito, si se proporciona.
    2. La variable de entorno ``RIR_LANCEDB_PATH``.
    3. ``<raiz del proyecto>/data/lancedb``.

    Nunca devuelve una ruta absoluta cableada a una unidad concreta: el
    proyecto debe poder moverse de disco o de maquina sin editar fuentes.
    """
    if db_path:
        return Path(db_path)

    from_env = os.environ.get(DB_PATH_ENV_VAR)
    if from_env:
        return Path(from_env)

    return PROJECT_ROOT / "data" / "lancedb"


def _sql_literal(value: str) -> str:
    """
    Convierte una cadena en un literal SQL seguro, duplicando las comillas
    simples segun el estandar SQL.

    LanceDB acepta predicados como cadena y no expone enlace de parametros,
    asi que el escape en origen es la unica defensa frente a la inyeccion.

        _sql_literal("o'brien")  ->  "'o''brien'"
    """
    if not isinstance(value, str):
        raise TypeError(
            f"Un literal SQL debe construirse desde str, no desde {type(value).__name__}"
        )
    return "'" + value.replace("'", "''") + "'"


class OpportunityRecord(BaseModel):
    """Modelo canónico de oportunidad persistida en LanceDB."""
    id: str
    text: str
    subreddit: str = ""
    author: str = "[deleted]"
    score: int = 0
    created_utc: float = 0.0
    buying_intent: str = "none"
    pain_severity: str = "none"
    urgency_tier: str = "LOW"
    opportunity_score: float = 0.0
    job_statement: str = ""
    current_solution: str | None = None
    workaround_detected: bool = False
    url: str | None = None
    #: "demo" o "reddit"; None = desconocida (filas anteriores a D-J).
    data_source: str | None = None
    vector: list[float] = Field(default_factory=list)


# Alias historico. El generador por hash vive ahora en embeddings.py y ha
# dejado de ser el proveedor por defecto: no es semantico.
DefaultTextEmbedder = HashEmbedder


class LanceDBStore:
    """
    Gestor de persistencia columnar serverless sobre LanceDB.
    """

    TABLE_NAME = "reddit_opportunities"

    def __init__(
        self,
        db_path: str | Path | None = None,
        vector_dim: int | None = None,
        embedder: TextEmbedder | None = None,
        allow_hash_fallback: bool = False
    ) -> None:
        """
        Args:
            db_path: ruta del almacen. Si se omite, se resuelve con
                ``resolve_db_path`` (entorno o raiz del proyecto).
            vector_dim: dimension del vector. Si se omite, la dicta el embedder.
            embedder: proveedor de embeddings. Si se omite, se pide el mejor
                disponible mediante ``get_embedder``.
            allow_hash_fallback: propaga a ``get_embedder`` la aceptacion
                explicita del degradado no semantico por hash.

        Raises:
            EmbeddingError: si no hay proveedor semantico y no se acepto el
                degradado.
            ValueError: si ``vector_dim`` contradice la dimension del embedder.
        """
        self.db_path = resolve_db_path(db_path)
        self.embedder = embedder or get_embedder(allow_hash_fallback=allow_hash_fallback)

        embedder_dim = getattr(self.embedder, "dim", None)
        if vector_dim is not None and embedder_dim is not None and vector_dim != embedder_dim:
            raise ValueError(
                f"vector_dim={vector_dim} contradice la dimension del embedder "
                f"({embedder_dim}). Omite vector_dim o pasa un embedder acorde."
            )
        self.vector_dim = vector_dim or embedder_dim or DEFAULT_VECTOR_DIM

        self.db_path.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(self.db_path))
        self._table = None
        self._init_table()

    def _get_schema(self) -> pa.Schema:
        """Define el esquema estricto PyArrow de la tabla columnar."""
        return pa.schema([
            pa.field("id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("subreddit", pa.string()),
            pa.field("author", pa.string()),
            pa.field("score", pa.int64()),
            pa.field("created_utc", pa.float64()),
            pa.field("buying_intent", pa.string()),
            pa.field("pain_severity", pa.string()),
            pa.field("urgency_tier", pa.string()),
            pa.field("opportunity_score", pa.float64()),
            pa.field("job_statement", pa.string()),
            pa.field("current_solution", pa.string()),
            pa.field("workaround_detected", pa.bool_()),
            pa.field("url", pa.string()),
            pa.field("data_source", pa.string(), nullable=True),
            pa.field("vector", pa.list_(pa.float32(), self.vector_dim))
        ])

    def _existing_tables(self) -> list[str]:
        """
        Nombres de las tablas ya presentes en el dataset.

        `list_tables()` sustituyó a `table_names()`, pero no devuelve una
        lista: devuelve un `ListTablesResponse`. Preguntarle `nombre in
        respuesta` da siempre falso, de modo que el almacén intentaba
        recrear una tabla existente y reventaba al abrir cualquier almacén
        con datos. Se normaliza aquí a una lista de nombres.
        """
        lister = getattr(self._db, "list_tables", None)
        if lister is None:
            return list(self._db.table_names())

        response = lister()
        return list(getattr(response, "tables", response))

    def _init_table(self) -> None:
        """Abre o crea la tabla de oportunidades en el dataset .lance."""
        tables = self._existing_tables()
        schema = self._get_schema()
        if self.TABLE_NAME in tables:
            self._table = self._db.open_table(self.TABLE_NAME)
            self._ensure_data_source_column()
        else:
            self._table = self._db.create_table(self.TABLE_NAME, schema=schema)

    def _ensure_data_source_column(self) -> None:
        """Añade `data_source` vacía a una tabla escrita antes de D-J.

        Queda NULL, que se lee «desconocida»: la rellena después
        `scripts/backfill_lancedb_source.py` cruzando con PostgreSQL.
        """
        if "data_source" not in self._table.schema.names:
            self._table.add_columns(pa.field("data_source", pa.string(), nullable=True))

    def insert_opportunities(self, records: Sequence[OpportunityRecord]) -> int:
        """
        Inserta un lote de oportunidades en la tabla .lance.
        Si algún registro carece de vector, lo autogenera mediante el embedder.
        """
        if not records:
            return 0

        rows = []
        for r in records:
            vec = r.vector
            if not vec or len(vec) != self.vector_dim:
                vec = self.embedder.embed_text(f"{r.text} {r.job_statement}")

            rows.append({
                "id": r.id,
                "text": r.text,
                "subreddit": r.subreddit or "",
                "author": r.author or "[deleted]",
                "score": int(r.score),
                "created_utc": float(r.created_utc),
                "buying_intent": r.buying_intent or "none",
                "pain_severity": r.pain_severity or "none",
                "urgency_tier": r.urgency_tier or "LOW",
                "opportunity_score": float(r.opportunity_score),
                "job_statement": r.job_statement or "",
                "current_solution": r.current_solution or "",
                "workaround_detected": bool(r.workaround_detected),
                "url": r.url or "",
                "data_source": r.data_source,
                "vector": [float(v) for v in vec]
            })

        self._table.add(rows)
        return len(rows)

    def search_vector(
        self,
        query_vector: list[float],
        limit: int = 10,
        filter_sql: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Ejecuta búsqueda por similitud vectorial densa (K-NN) con filtrado opcional SQL.
        """
        query = self._table.search(query_vector).limit(limit)
        if filter_sql:
            query = query.where(filter_sql)
        return query.to_list()

    def search_text(
        self,
        query_text: str,
        limit: int = 10,
        filter_sql: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Genera el embedding de la consulta en lenguaje natural y busca en el espacio vectorial.
        """
        vec = self.embedder.embed_text(query_text)
        return self.search_vector(vec, limit=limit, filter_sql=filter_sql)

    def count_records(self) -> int:
        """Retorna el número total de filas en la tabla."""
        return self._table.count_rows()

    def ids_where(self, filter_sql: str, limit: int | None = None) -> list[str]:
        """
        Devuelve los identificadores que satisfacen un predicado SQL.

        Proyecta unicamente la columna `id`: recuperar la fila entera traeria
        tambien su vector, que es con diferencia la columna mas pesada.
        """
        if not filter_sql:
            return []
        effective_limit = limit or max(self.count_records(), 1)
        rows = (
            self._table.search()
            .where(filter_sql)
            .select(["id"])
            .limit(effective_limit)
            .to_list()
        )
        return [str(row["id"]) for row in rows]

    def filter_ids(self, candidate_ids: Sequence[str], filter_sql: str) -> set:
        """
        Restringe un conjunto acotado de identificadores a los que ademas
        satisfacen el predicado.

        Es la via que usa el motor hibrido para aplicar el filtro a la rama
        lexica sin escanear la tabla completa: el coste queda ligado al numero
        de candidatos, no al tamano del almacen.
        """
        ids = [str(i) for i in candidate_ids]
        if not ids:
            return set()
        if not filter_sql:
            return set(ids)

        in_clause = ", ".join(_sql_literal(i) for i in ids)
        predicate = f"({filter_sql}) AND id IN ({in_clause})"
        rows = (
            self._table.search()
            .where(predicate)
            .select(["id"])
            .limit(len(ids))
            .to_list()
        )
        return {str(row["id"]) for row in rows}

    def get_by_id(self, record_id: str) -> dict[str, Any] | None:
        """Recupera un registro puntual por su clave primaria."""
        results = (
            self._table.search()
            .where(f"id = {_sql_literal(record_id)}")
            .limit(1)
            .to_list()
        )
        return results[0] if results else None

    def delete_by_id(self, record_id: str) -> bool:
        """
        Elimina un registro concreto.

        Returns:
            True solo si el borrado redujo efectivamente el numero de filas.
        """
        predicate = f"id = {_sql_literal(record_id)}"
        try:
            before = self.count_records()
            self._table.delete(predicate)
            return self.count_records() < before
        # Fallos del almacén (disco, dataset, predicado rechazado). Un id que
        # no es texto lanza TypeError antes y llega a quien llama.
        except (OSError, RuntimeError, ValueError) as e:
            logger.error(f"Error eliminando registro {record_id}: {e}")
            return False
