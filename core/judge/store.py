"""
Persistencia del juez (F3.8)
============================

- PostgresLabelCache: la caché de etiquetas de `labels.label_items` en
  `evidence_labels`, por (hash de contenido, etiquetador). Síncrona, como
  el etiquetado, que corre en un hilo aparte.
- top_verdicts: el Top 6 de una ejecución, ordenado por veredicto
  (CONSTRUIR primero) y luego por puntaje, y aparte el resto en el mismo
  orden (C1: Radar y panel leen lo mismo). Si hay menos de 6 CONSTRUIR se
  dice cuántos hay y por qué; no se rellena (AUD-007).
- recent_evidence: el feed de evidencia más reciente, sin duplicados y con
  atribución; sin autores (R9).
- verdict_detail: un veredicto con toda su evidencia (texto entero) y su
  ejecución, para el dossier y el plan de la Fase E.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import TYPE_CHECKING, Any

import psycopg
from psycopg.rows import dict_row

from core.sources.attribution import attribution_fields
from core.storage.identity import Previo
from core.storage.postgres_store import DEFAULT_TENANT_ID, SCHEMA_OPTIONS

from .gates import normalizar_compuertas
from .labels import VerifiedLabel

if TYPE_CHECKING:
    from core.storage.postgres_store import PostgresStore

#: Tamaño del Top (AUD-007).
TOP_TARGET = 6
#: Fragmento de cada evidencia que se enseña (el texto entero vive en la base).
EXCERPT_CHARS = 280


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


#: Por qué una ejecución juzgada no tiene veredictos (AUD2-001): el juez solo
#: forma nichos con dolor verificado y parecido entre sí.
SIN_NICHOS = ("El juez no formó ningún nicho en esta ejecución: no hubo bastantes piezas con "
              "un dolor verificado y parecido entre sí.")


async def marcar_juzgada(store: PostgresStore, run_id: str, *, construir: int) -> None:
    """Deja constancia de que el juez pasó por la ejecución, con o sin nichos
    (top_n_*: objetivo, cuántos CONSTRUIR y por qué no se llegó)."""
    encontrados = min(construir, TOP_TARGET)
    motivo = None if encontrados == TOP_TARGET else "datos_insuficientes"
    await store._fetchone_returning(
        """
        UPDATE pipeline_runs SET top_n_target = %s, top_n_found = %s, top_n_reason = %s
         WHERE tenant_id = %s AND id = %s RETURNING id
        """,
        (TOP_TARGET, encontrados, motivo, store.tenant_id, run_id),
    )


async def latest_judged_run(store: PostgresStore) -> str | None:
    """La última ejecución que pasó por el juez, aunque no formase nichos; las
    anteriores a la marca se reconocen por tener veredictos."""
    fila = await store._fetchone(
        """
        SELECT r.id::text AS run_id FROM pipeline_runs r
         WHERE r.tenant_id = %s
           AND (r.top_n_target IS NOT NULL
                OR EXISTS (SELECT 1 FROM niche_verdicts v WHERE v.run_id = r.id))
         ORDER BY r.started_at DESC LIMIT 1
        """,
        (store.tenant_id,),
    )
    return fila["run_id"] if fila else None


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


#: Columnas de un veredicto con sus miembros (Top 6 y detalle leen lo mismo).
_VEREDICTO = """
        SELECT v.id::text AS id, v.run_id::text AS run_id,
               v.opportunity_id::text AS opportunity_id, v.cluster_key,
               v.keywords, v.verdict, v.rule, v.score::float8 AS score, v.weights_version,
               v.missing, v.gates, v.dimensions, v.advocate, v.member_count,
               v.labeler_version, v.clustering_version,
               COALESCE(array_agg(ce.evidence_id ORDER BY ce.evidence_id)
                        FILTER (WHERE ce.evidence_id IS NOT NULL), '{}') AS member_ids
          FROM niche_verdicts v
          LEFT JOIN cluster_evidence ce ON ce.verdict_id = v.id
"""
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


async def verdict_detail(store: PostgresStore, verdict_id: str) -> dict[str, Any] | None:
    """El veredicto con toda su evidencia (texto entero, sin autor) y su
    ejecución; None si no existe o el id no es un uuid."""
    if not _UUID.fullmatch(verdict_id):
        return None
    fila = await store._fetchone(
        _VEREDICTO + " WHERE v.tenant_id = %s AND v.id = %s GROUP BY v.id",
        (store.tenant_id, verdict_id),
    )
    if fila is None:
        return None
    detalle = dict(fila)
    detalle["gates"] = normalizar_compuertas(detalle.get("gates") or [])
    run = await store._fetchone(
        "SELECT id::text AS id, started_at, parameters, data_source, trigger_source"
        " FROM pipeline_runs WHERE tenant_id = %s AND id = %s",
        (store.tenant_id, detalle["run_id"]),
    )
    detalle["run"] = dict(run) if run else None
    evidencia = await store._fetchall(
        """
        SELECT id, source, community, kind, title, content AS text, url, created_at, data_source
          FROM evidence_items WHERE tenant_id = %s AND id = ANY(%s)
         ORDER BY created_at DESC, id
        """,
        (store.tenant_id, list(detalle["member_ids"])),
    )
    detalle["evidence"] = [
        {**dict(e), "attribution": attribution_fields(e["source"], e["community"], e["url"])}
        for e in evidencia
    ]
    detalle["current_versions"] = current_versions()
    return detalle


async def top_verdicts(store: PostgresStore, run_id: str) -> dict[str, Any]:
    filas = await store._fetchall(
        _VEREDICTO + """
         WHERE v.tenant_id = %s AND v.run_id = %s
         GROUP BY v.id
         ORDER BY CASE v.verdict WHEN 'CONSTRUIR' THEN 0 WHEN 'INVESTIGAR MÁS' THEN 1 ELSE 2 END,
                  v.score DESC, v.cluster_key
        """,
        (store.tenant_id, run_id),
    )
    todos = [{**dict(f), "gates": normalizar_compuertas(f["gates"] or [])} for f in filas]
    await _con_evidencia(store, todos)
    veredictos, resto = todos[:TOP_TARGET], todos[TOP_TARGET:]
    construir = sum(1 for f in filas if f["verdict"] == "CONSTRUIR")
    motivo = None
    if not filas:
        motivo = SIN_NICHOS
    elif construir < TOP_TARGET:
        motivo = (f"Solo {construir} de {TOP_TARGET} nichos pasan todas las compuertas "
                  "y el abogado del diablo; el resto no se rellena.")
    return {"run_id": run_id, "target": TOP_TARGET, "build_count": construir,
            "reason": motivo, "verdicts": veredictos, "rest": resto,
            "current_versions": current_versions()}


async def recent_evidence(store: PostgresStore, limit: int) -> list[dict[str, Any]]:
    """Evidencia canónica más reciente (los duplicados apuntan a otra)."""
    filas = await store._fetchall(
        """
        SELECT e.id, e.source, e.community, e.kind, e.title, e.content, e.url,
               e.created_at, e.data_source
          FROM evidence_items e
         WHERE e.tenant_id = %s
           AND NOT EXISTS (SELECT 1 FROM evidence_duplicates d
                            WHERE d.tenant_id = e.tenant_id AND d.duplicate_id = e.id)
         ORDER BY e.created_at DESC, e.id
         LIMIT %s
        """,
        (store.tenant_id, limit),
    )
    return [
        {"id": f["id"], "source": f["source"], "community": f["community"], "kind": f["kind"],
         "title": f["title"], "excerpt": f["content"][:EXCERPT_CHARS], "url": f["url"],
         "created_at": f["created_at"].isoformat(), "data_source": f["data_source"],
         "attribution": attribution_fields(f["source"], f["community"], f["url"])}
        for f in filas
    ]


def current_versions() -> dict[str, str]:
    """Versiones con las que juzga el código actual (B4): lo distinto es antiguo."""
    from .clustering import CLUSTERING_VERSION
    from .dimensions import WEIGHTS_VERSION
    from .labels import LABELER_VERSION

    return {"labeler": LABELER_VERSION, "clustering": CLUSTERING_VERSION,
            "weights": WEIGHTS_VERSION}


async def _con_evidencia(store: PostgresStore, veredictos: list[dict[str, Any]]) -> None:
    """Añade a cada veredicto su corroboración por fuente y su evidencia con
    fragmento y atribución obligatoria (insignia, sitio, URL; D-SE3)."""
    ids = sorted({m for v in veredictos for m in v["member_ids"]})
    if not ids:
        for v in veredictos:
            v["corroboration"], v["evidence"] = {}, []
        return
    filas = await store._fetchall(
        """
        SELECT id, source, community, url, content, created_at
          FROM evidence_items WHERE tenant_id = %s AND id = ANY(%s)
        """,
        (store.tenant_id, ids),
    )
    por_id = {f["id"]: f for f in filas}
    for v in veredictos:
        miembros = [por_id[m] for m in v["member_ids"] if m in por_id]
        v["corroboration"] = dict(Counter(m["source"] for m in miembros))
        v["evidence"] = [
            {"id": m["id"], "source": m["source"], "excerpt": m["content"][:EXCERPT_CHARS],
             "created_at": m["created_at"].isoformat(),
             "attribution": attribution_fields(m["source"], m["community"], m["url"])}
            for m in sorted(miembros, key=lambda m: m["created_at"], reverse=True)
        ]
