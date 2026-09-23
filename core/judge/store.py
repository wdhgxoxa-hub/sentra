"""
Persistencia del juez (F3.8)
============================

- PostgresLabelCache: la caché de etiquetas de `labels.label_items` en
  `evidence_labels`, por (hash de contenido, etiquetador). Síncrona, como
  el etiquetado, que corre en un hilo aparte.
- top_verdicts: el Top 6 de una ejecución, ordenado por veredicto
  (CONSTRUIR primero) y luego por puntaje. Si hay menos de 6 CONSTRUIR se
  dice cuántos hay y por qué; no se rellena (AUD-007).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import psycopg
from psycopg.rows import dict_row

from core.storage.identity import Previo
from core.storage.postgres_store import DEFAULT_TENANT_ID, SCHEMA_OPTIONS

from .labels import VerifiedLabel

if TYPE_CHECKING:
    from core.storage.postgres_store import PostgresStore

#: Tamaño del Top (AUD-007).
TOP_TARGET = 6


class PostgresLabelCache:
    def __init__(self, dsn: str, tenant_id: str = DEFAULT_TENANT_ID) -> None:
        self.dsn = dsn
        self.tenant_id = tenant_id

    def _conectar(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(self.dsn, row_factory=dict_row, options=SCHEMA_OPTIONS)

    def get(self, content_hash: str, labeler: str) -> VerifiedLabel | None:
        with self._conectar() as conn:
            fila = conn.execute(
                "SELECT label FROM evidence_labels "
                "WHERE tenant_id = %s AND content_hash = %s AND labeler = %s",
                (self.tenant_id, content_hash, labeler)).fetchone()
        return VerifiedLabel.model_validate(fila["label"]) if fila else None

    def put(self, label: VerifiedLabel) -> None:
        with self._conectar() as conn:
            conn.execute(
                """
                INSERT INTO evidence_labels (tenant_id, content_hash, labeler, label)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id, content_hash, labeler) DO UPDATE SET label = EXCLUDED.label
                """,
                (self.tenant_id, label.content_hash, label.labeler, json.dumps(label.model_dump())))


async def previous_identities(store: PostgresStore) -> list[Previo]:
    """Última lectura de cada oportunidad juzgada (identidad estable D-G)."""
    filas = await store._fetchall(
        """
        SELECT DISTINCT ON (v.opportunity_id) v.opportunity_id::text AS opportunity_id,
               v.keywords, array_agg(ce.evidence_id) AS member_ids
          FROM niche_verdicts v
          JOIN cluster_evidence ce ON ce.verdict_id = v.id
         WHERE v.tenant_id = %s AND v.opportunity_id IS NOT NULL
         GROUP BY v.id
         ORDER BY v.opportunity_id, v.created_at DESC
        """,
        (store.tenant_id,),
    )
    return [Previo(f["opportunity_id"], set(f["member_ids"]), set(f["keywords"] or []))
            for f in filas]


async def top_verdicts(store: PostgresStore, run_id: str) -> dict[str, Any]:
    filas = await store._fetchall(
        """
        SELECT v.id::text AS id, v.opportunity_id::text AS opportunity_id, v.cluster_key,
               v.keywords, v.verdict, v.rule, v.score::float8 AS score, v.weights_version,
               v.missing, v.gates, v.dimensions, v.advocate, v.member_count,
               COALESCE(array_agg(ce.evidence_id ORDER BY ce.evidence_id)
                        FILTER (WHERE ce.evidence_id IS NOT NULL), '{}') AS member_ids
          FROM niche_verdicts v
          LEFT JOIN cluster_evidence ce ON ce.verdict_id = v.id
         WHERE v.tenant_id = %s AND v.run_id = %s
         GROUP BY v.id
         ORDER BY CASE v.verdict WHEN 'CONSTRUIR' THEN 0 WHEN 'INVESTIGAR MÁS' THEN 1 ELSE 2 END,
                  v.score DESC, v.cluster_key
         LIMIT %s
        """,
        (store.tenant_id, run_id, TOP_TARGET),
    )
    construir = sum(1 for f in filas if f["verdict"] == "CONSTRUIR")
    motivo = None
    if construir < TOP_TARGET:
        motivo = (f"Solo {construir} de {TOP_TARGET} nichos pasan todas las compuertas "
                  "y el abogado del diablo; el resto no se rellena.")
    return {"run_id": run_id, "target": TOP_TARGET, "build_count": construir,
            "reason": motivo, "verdicts": [dict(f) for f in filas]}
