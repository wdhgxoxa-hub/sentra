"""
Búsqueda sobre la evidencia multifuente (D-C4)
==============================================

Dos ramas que fallan de forma distinta, fusionadas con RRF:

- Densa: vectores e5 de `evidence_e5` (con el prefijo de consulta de e5).
  Encuentra paráfrasis y la misma queja en otro idioma.
- Léxica: búsqueda de texto de PostgreSQL sobre título y texto de
  `evidence_items`, con la configuración `simple` (sin lematizar: sirve
  igual para español e inglés). Rescata nombres propios y términos exactos.

Cada resultado dice qué rama lo encontró y en qué puesto, lleva su
atribución (R5) y ningún autor (R9). Los duplicados no salen: apuntan a su
pieza canónica.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.sources.attribution import attribution_fields

if TYPE_CHECKING:
    from core.storage.postgres_store import PostgresStore

    from .vectors import EvidenceVectorStore

#: Constante de RRF (la del artículo original y la de la búsqueda antigua).
RRF_K = 60
#: Fragmento que se enseña de cada resultado.
EXCERPT_CHARS = 280

_TEXTO = "coalesce(e.title, '') || ' ' || e.content"


@dataclass(frozen=True)
class Ranking:
    id: str
    score: float
    dense_rank: int | None
    lexical_rank: int | None


def fuse_rrf(dense: Sequence[str], lexical: Sequence[str], k: int = RRF_K) -> list[Ranking]:
    """Fusión por rango recíproco; a igual puntuación, por id (estable)."""
    puestos_d = {i: n for n, i in enumerate(dense, start=1)}
    puestos_l = {i: n for n, i in enumerate(lexical, start=1)}
    fusion = []
    for i in puestos_d.keys() | puestos_l.keys():
        d, lx = puestos_d.get(i), puestos_l.get(i)
        score = (1 / (k + d) if d else 0.0) + (1 / (k + lx) if lx else 0.0)
        fusion.append(Ranking(i, score, d, lx))
    return sorted(fusion, key=lambda r: (-r.score, r.id))


def dense_ids(vectors: EvidenceVectorStore, query: str, limit: int) -> list[str]:
    return [fila["id"] for fila in vectors.similar(query, limit=limit)]


async def lexical_ids(store: PostgresStore, query: str, limit: int) -> list[str]:
    """Ids canónicos por relevancia léxica (ts_rank_cd); sin términos útiles, nada.

    Basta cualquiera de los términos (OR) y los de 4 letras o más valen como
    prefijo (los más cortos, tal cual: «en» o «s» casarían con casi todo): con
    `simple` no hay lematización, y exigirlos todos dejaba sin resultados
    consultas normales como «notification preferences» contra la evidencia
    real. ts_rank_cd pone primero lo que coincide con más términos. Los
    términos salen de to_tsvector y se citan en SQL (comillas y barras
    escapadas), así que la consulta nunca rompe la sintaxis de tsquery.
    """
    filas = await store._fetchall(
        f"""
        WITH terminos AS (
            SELECT to_tsquery('simple', string_agg(
                       '''' || replace(replace(l, E'\\\\', E'\\\\\\\\'), '''', '''''') || '''' || CASE WHEN length(l) >= 4 THEN ':*' ELSE '' END,
                       ' | ')) AS q
              FROM unnest(tsvector_to_array(to_tsvector('simple', %s))) AS l
        )
        SELECT e.id
          FROM evidence_items e, terminos t
         WHERE e.tenant_id = %s
           AND t.q IS NOT NULL
           AND to_tsvector('simple', {_TEXTO}) @@ t.q
           AND NOT EXISTS (SELECT 1 FROM evidence_duplicates d
                            WHERE d.tenant_id = e.tenant_id AND d.duplicate_id = e.id)
         ORDER BY ts_rank_cd(to_tsvector('simple', {_TEXTO}), t.q) DESC, e.id
         LIMIT %s
        """,
        (query, store.tenant_id, limit),
    )
    return [f["id"] for f in filas]


async def evidence_hits(store: PostgresStore, fusion: Sequence[Ranking]) -> list[dict[str, Any]]:
    """Las piezas de la fusión, en su orden, con atribución; sin duplicados."""
    if not fusion:
        return []
    filas = await store._fetchall(
        """
        SELECT e.id, e.source, e.community, e.kind, e.title, e.content, e.url,
               e.created_at, e.data_source
          FROM evidence_items e
         WHERE e.tenant_id = %s AND e.id = ANY(%s)
           AND NOT EXISTS (SELECT 1 FROM evidence_duplicates d
                            WHERE d.tenant_id = e.tenant_id AND d.duplicate_id = e.id)
        """,
        (store.tenant_id, [r.id for r in fusion]),
    )
    por_id = {f["id"]: f for f in filas}
    return [
        {"id": f["id"], "source": f["source"], "community": f["community"], "kind": f["kind"],
         "title": f["title"], "excerpt": f["content"][:EXCERPT_CHARS], "url": f["url"],
         "created_at": f["created_at"].isoformat(), "data_source": f["data_source"],
         "attribution": attribution_fields(f["source"], f["community"], f["url"]),
         "rrf_score": r.score, "dense_rank": r.dense_rank, "lexical_rank": r.lexical_rank}
        for r in fusion if (f := por_id.get(r.id)) is not None
    ]
