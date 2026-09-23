"""
Vectores de la evidencia multifuente (F2.3, D-M2)
=================================================

Tabla LanceDB propia (`evidence_e5`), separada de la de la pipeline de
Reddit: su modelo es multilingüe (intfloat/multilingual-e5-large, 1024
dimensiones) y cambiar de modelo obliga a recalcular todos los vectores.
La usan la deduplicación entre fuentes (F2.6) y el clustering (F3).

Cada fila lleva el id global y la fuente, y ningún autor (R9).
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa
from lancedb.table import Table

from core.storage.embeddings import MULTILINGUAL_MODEL_NAME, TextEmbedder
from core.storage.lancedb_store import _sql_literal, resolve_db_path

from .model import EvidenceItem

#: Texto que se guarda junto al vector; el completo vive en PostgreSQL.
MAX_TEXT_CHARS = 2_000


class EvidenceVectorStore:
    """Vectores de `EvidenceItem`, con upsert idempotente por id global."""

    TABLE_NAME = "evidence_e5"
    DEFAULT_MODEL = MULTILINGUAL_MODEL_NAME

    def __init__(self, db_path: str | os.PathLike[str] | None = None,
                 embedder: TextEmbedder | None = None) -> None:
        if embedder is None:
            from core.storage.embeddings import FastEmbedEmbedder

            embedder = FastEmbedEmbedder(self.DEFAULT_MODEL)
        self.embedder = embedder
        self.dim = len(embedder.embed_text("dimension probe"))
        ruta = Path(db_path) if db_path is not None else resolve_db_path()
        ruta.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(ruta))
        self._table: Table = self._open_table()

    def _schema(self) -> pa.Schema:
        return pa.schema([
            pa.field("id", pa.string()),
            pa.field("source", pa.string()),
            pa.field("community", pa.string()),
            pa.field("kind", pa.string()),
            pa.field("text", pa.string()),
            pa.field("data_source", pa.string(), nullable=True),
            pa.field("created_at", pa.float64()),
            pa.field("vector", pa.list_(pa.float32(), self.dim)),
        ])

    def _open_table(self) -> Table:
        respuesta = self._db.list_tables()
        nombres = list(getattr(respuesta, "tables", respuesta))
        if self.TABLE_NAME in nombres:
            return self._db.open_table(self.TABLE_NAME)
        return self._db.create_table(self.TABLE_NAME, schema=self._schema())

    def columnas(self) -> list[str]:
        return list(self._table.schema.names)

    def count(self) -> int:
        return self._table.count_rows()

    @staticmethod
    def _texto(item: EvidenceItem) -> str:
        return f"{item.title}\n{item.text}" if item.title else item.text

    def embed(self, items: Sequence[EvidenceItem]) -> dict[str, list[float]]:
        """Vectores por id global, con el mismo texto que se guarda."""
        if not items:
            return {}
        vectores = self.embedder.embed_batch([self._texto(i) for i in items])
        return {i.id: list(v) for i, v in zip(items, vectores, strict=True)}

    def upsert(
        self,
        items: Sequence[EvidenceItem],
        vectors: Mapping[str, Sequence[float]] | None = None,
    ) -> int:
        """Inserta o actualiza por id global. Devuelve cuántos recibió.

        Los vectores ya calculados (`vectors`, por id) se reutilizan; solo se
        calculan los que faltan.
        """
        if not items:
            return 0
        dados = dict(vectors or {})
        dados |= self.embed([i for i in items if i.id not in dados])
        vectores = [dados[i.id] for i in items]
        filas = [
            {
                "id": item.id,
                "source": item.source,
                "community": item.community,
                "kind": item.kind,
                "text": item.text[:MAX_TEXT_CHARS],
                "data_source": item.data_source,
                "created_at": item.created_at.timestamp(),
                "vector": vector,
            }
            for item, vector in zip(items, vectores, strict=True)
        ]
        (
            self._table.merge_insert("id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(filas)
        )
        return len(filas)

    def get(self, evidence_id: str) -> dict[str, Any] | None:
        filas = (
            self._table.search().where(f"id = {_sql_literal(evidence_id)}").limit(1).to_list()
        )
        return filas[0] if filas else None

    def similar(self, text: str, limit: int = 10) -> list[dict[str, Any]]:
        """Filas más parecidas a una consulta (con el prefijo de consulta de e5)."""
        return self._table.search(self.embedder.embed_query(text)).limit(limit).to_list()

    def vectors(self, ids: Sequence[str]) -> dict[str, list[float]]:
        """Vector de cada id que exista (los que no, no aparecen)."""
        if not ids:
            return {}
        lista = ", ".join(_sql_literal(i) for i in ids)
        filas = self._table.search().where(f"id IN ({lista})").limit(len(ids)).to_list()
        return {f["id"]: list(f["vector"]) for f in filas}
