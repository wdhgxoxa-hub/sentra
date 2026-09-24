"""
Re-juicio de un escaneo guardado (AUD2-001, 6.4)
===============================================

Vuelve a pasar el juez actual por la evidencia de un escaneo ya guardado,
sin escanear de nuevo: la evidencia canónica del escaneo de origen (sin
duplicados), sus vectores e5 y su tema. El resultado es una ejecución nueva
«rejuicio» (con `rejuicio_de` en sus parámetros), marcada como juzgada; el
escaneo de origen no se toca. Lo mismo que hace el escaneo tras guardar
(core/orchestration/sidecar/multiscan.py), pero sobre lo que ya hay.
`scripts/rejuzgar.py` lo lanza con el proveedor y los vectores reales.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

from core.evidence.model import Engagement, EvidenceItem
from core.llm.base import JsonGenerator
from core.storage.postgres_store import PostgresStore, run_async

from .labels import LabelCache
from .pipeline import run_judge
from .store import marcar_juzgada, previous_identities

#: trigger_source de las ejecuciones que re-juzgan un escaneo guardado.
TRIGGER_REJUICIO = "rejuicio"


async def evidencia_de_ejecucion(store: PostgresStore, run_id: str) -> list[EvidenceItem]:
    """La evidencia canónica que guardó un escaneo (los duplicados apuntan a otra)."""
    filas = await store._fetchall(
        """
        SELECT e.id, e.source, e.community, e.kind, e.title, e.content AS text, e.url, e.author_hash,
               e.created_at, e.fetched_at, e.language, e.thread_id, e.score, e.replies, e.reactions,
               e.views, e.native_metrics, e.data_source, e.run_id::text AS run_id
          FROM evidence_items e
         WHERE e.tenant_id = %s AND e.run_id = %s
           AND NOT EXISTS (SELECT 1 FROM evidence_duplicates d
                            WHERE d.tenant_id = e.tenant_id AND d.duplicate_id = e.id)
         ORDER BY e.created_at, e.id
        """,
        (store.tenant_id, run_id),
    )
    return [
        EvidenceItem(**{k: f[k] for k in f if k not in ("score", "replies", "reactions", "views")},
                     engagement=Engagement(score=f["score"], replies=f["replies"],
                                           reactions=f["reactions"], views=f["views"]))
        for f in filas
    ]


def rejuzgar(
    dsn: str,
    run_origen: str,
    *,
    provider: JsonGenerator | None,
    model: str | None,
    cache: LabelCache,
    vectores: Callable[[Sequence[str]], Mapping[str, Sequence[float]]],
    vectores_frase: Callable[[Mapping[str, str]], Mapping[str, Sequence[float]]],
    now: datetime,
) -> tuple[str, dict[str, Any]]:
    """Re-juzga el escaneo `run_origen`; devuelve (id de la ejecución nueva, resumen)."""

    async def correr() -> tuple[str, dict[str, Any]]:
        async with PostgresStore(dsn=dsn) as store:
            origen = await store._fetchone(
                "SELECT subreddit_name, parameters FROM pipeline_runs WHERE tenant_id = %s AND id = %s",
                (store.tenant_id, run_origen),
            )
            if origen is None:
                raise ValueError(f"No hay ninguna ejecución {run_origen}")
            parametros = dict(origen["parameters"] or {})
            items = await evidencia_de_ejecucion(store, run_origen)
            juicio = run_judge(items, vectores([i.id for i in items]), provider=provider, model=model,
                               cache=cache, now=now, vectores_frase=vectores_frase,
                               previous=await previous_identities(store),
                               tema=list(parametros.get("keywords") or []))
            nueva = await store.start_run(origen["subreddit_name"], trigger_source=TRIGGER_REJUICIO,
                                          parameters={**parametros, "rejuicio_de": run_origen},
                                          data_source="real")
            await store.save_verdicts(nueva, juicio.verdicts)
            # finish_run reescribe top_n_* (sus valores por defecto son None):
            # se cierra primero y se marca después, o la marca se perdería.
            await store.finish_run(nueva, {"fetched": len(items), "stored": len(juicio.verdicts)})
            await marcar_juzgada(store, nueva, construir=sum(
                1 for v in juicio.verdicts if v["verdict"] == "CONSTRUIR"))
            return nueva, juicio.summary

    return run_async(correr())
