"""
Adaptador PostgreSQL
====================

Lo que el escaneo multifuente y el juez guardan en PostgreSQL: ejecuciones
(`pipeline_runs`), evidencia (`evidence_items`) y sus duplicados, y los
veredictos del juez con sus miembros. PostgreSQL es el rastro relacional
auditable; los vectores viven en LanceDB (`evidence_e5`).

La escritura y la lectura de la pipeline antigua de Reddit (posts, señales,
clusters, oportunidades, tablero, feed) se retiraron en C2: nadie las
llamaba. Sus tablas se conservan sin escrituras (docs/pipeline-antigua.md).

Uso:

    async with PostgresStore() as store:
        run_id = await store.start_run("perfil", trigger_source="multifuente")
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections.abc import Coroutine, Sequence
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Self

from core.evidence.model import EvidenceItem, content_fingerprint

if TYPE_CHECKING:
    from psycopg import AsyncConnection

    from core.sources.dedup import Duplicate

logger = logging.getLogger(__name__)

def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """
    Ejecuta una corrutina con un bucle de eventos compatible con psycopg.

    En Windows, asyncio usa `ProactorEventLoop` por defecto y psycopg se
    niega a funcionar sobre él; necesita un `SelectorEventLoop`. Se resuelve
    aquí, y no cambiando la política global de asyncio al importar el
    módulo, porque eso afectaría a todo el proceso sin avisar.
    """
    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            return runner.run(coro)
    return asyncio.run(coro)

# Tenant de la instalación local: lo crea la migración 001 (sql/migrations/001_initial_schema.sql).
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"

#: Base por defecto: la misma URL que ui/src-tauri/src/db.rs (sqlx solo entiende
#: URL; psycopg, URL o palabras clave).
DEFAULT_DSN = "postgresql://postgres@localhost:5432/reddit_intelligence_radar"
#: AUD2-011: una sola variable para Rust y Python. Antes Rust leía RIR_PG_URL
#: y Python RIR_PG_DSN: con una puesta, solo media aplicación iba a otra base.
DSN_ENV_VAR = "RIR_PG_URL"
#: Nombre antiguo de Python: se acepta un tiempo, con aviso.
DSN_ENV_VAR_ANTIGUA = "RIR_PG_DSN"


def resolver_dsn(explicito: str | None = None) -> str:
    """La base a la que conectar: la indicada, RIR_PG_URL, RIR_PG_DSN (antigua,
    con aviso) o la de por defecto. El único sitio que la resuelve."""
    if explicito:
        return explicito
    valor = os.environ.get(DSN_ENV_VAR, "").strip()
    if valor:
        return valor
    antigua = os.environ.get(DSN_ENV_VAR_ANTIGUA, "").strip()
    if antigua:
        logger.warning("%s está obsoleta: usa %s (la lee también la interfaz)",
                       DSN_ENV_VAR_ANTIGUA, DSN_ENV_VAR)
        return antigua
    return DEFAULT_DSN

# El adaptador fija el search_path en la conexión, no por sentencia: así
# sobrevive a los rollbacks, que revierten cualquier SET hecho dentro de
# la transacción.
SCHEMA_OPTIONS = "-c search_path=radar,public"


# =====================================================================
# Repositorio
# =====================================================================

class PostgresStore:
    """
    Repositorio asíncrono sobre el esquema `radar`.

    Abre una conexión propia y la mantiene mientras viva el contexto:

        async with PostgresStore() as store:
            await store.upsert_evidence(items, run_id)

    Los autores llegan ya como hash salado en `EvidenceItem.author_hash`
    (R9): este adaptador no ve ningún nombre.
    """

    def __init__(self, dsn: str | None = None, tenant_id: str = DEFAULT_TENANT_ID) -> None:
        self.dsn = resolver_dsn(dsn)
        self.tenant_id = tenant_id
        self._conn: AsyncConnection[dict[str, Any]] | None = None

    # -- Evidencia y veredictos (D-M1) -------------------------------------

    async def upsert_evidence(
        self, items: Sequence[EvidenceItem], run_id: str | None = None
    ) -> int:
        """Guarda evidencia de cualquier fuente en evidence_items (F2.3).

        Upsert idempotente por id global: lo que cambia (texto, interacción,
        métricas) se actualiza; la procedencia de una fila ya guardada no
        cambia. Devuelve cuántas piezas recibió.
        """
        for item in items:
            await self.connection.execute(
                """
                INSERT INTO evidence_items (id, tenant_id, source, community, kind, title,
                    content, url, author_hash, created_at, fetched_at, language, thread_id,
                    score, replies, reactions, views, native_metrics, data_source, run_id,
                    content_hash)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (tenant_id, id) DO UPDATE SET
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    content_hash = EXCLUDED.content_hash,
                    score = EXCLUDED.score,
                    replies = EXCLUDED.replies,
                    reactions = EXCLUDED.reactions,
                    views = EXCLUDED.views,
                    native_metrics = EXCLUDED.native_metrics,
                    fetched_at = EXCLUDED.fetched_at,
                    language = COALESCE(EXCLUDED.language, evidence_items.language),
                    run_id = COALESCE(EXCLUDED.run_id, evidence_items.run_id),
                    data_source = COALESCE(evidence_items.data_source, EXCLUDED.data_source)
                """,
                (
                    item.id, self.tenant_id, item.source, item.community, item.kind,
                    item.title, item.text, item.url, item.author_hash, item.created_at,
                    item.fetched_at, item.language, item.thread_id,
                    item.engagement.score, item.engagement.replies,
                    item.engagement.reactions, item.engagement.views,
                    json.dumps(item.native_metrics, default=str), item.data_source,
                    run_id or item.run_id, content_fingerprint(item.text),
                ),
            )
        await self.connection.commit()
        return len(items)

    async def save_verdicts(self, run_id: str, verdicts: Sequence[dict[str, Any]]) -> list[str]:
        """Guarda los veredictos del juez de una ejecución y sus miembros (F3.8).

        Cada veredicto trae cluster_key, keywords, verdict, rule, score,
        weights_version, missing, gates, dimensions, advocate, member_ids y
        opportunity_id. Devuelve los ids creados.
        """
        ids: list[str] = []
        for v in verdicts:
            fila = await self._fetchone_returning(
                """
                INSERT INTO niche_verdicts (tenant_id, run_id, opportunity_id, cluster_key,
                    keywords, verdict, rule, score, weights_version, missing, gates,
                    dimensions, advocate, member_count, labeler_version, clustering_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id, cluster_key) DO UPDATE SET
                    verdict = EXCLUDED.verdict, rule = EXCLUDED.rule, score = EXCLUDED.score,
                    missing = EXCLUDED.missing, gates = EXCLUDED.gates,
                    dimensions = EXCLUDED.dimensions, advocate = EXCLUDED.advocate,
                    member_count = EXCLUDED.member_count,
                    labeler_version = EXCLUDED.labeler_version,
                    clustering_version = EXCLUDED.clustering_version
                RETURNING id
                """,
                (
                    self.tenant_id, run_id, v.get("opportunity_id"), v["cluster_key"],
                    list(v.get("keywords") or []), v["verdict"], v["rule"],
                    round(float(v["score"]), 2), v["weights_version"], list(v.get("missing") or []),
                    json.dumps(v["gates"], default=str), json.dumps(v["dimensions"], default=str),
                    json.dumps(v.get("advocate") or {}, default=str), len(v["member_ids"]),
                    v.get("labeler_version"), v["clustering_version"],
                ),
            )
            verdict_id = str(fila["id"])
            for evidencia in v["member_ids"]:
                await self.connection.execute(
                    """
                    INSERT INTO cluster_evidence (tenant_id, verdict_id, evidence_id)
                    VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
                    """,
                    (self.tenant_id, verdict_id, evidencia),
                )
            ids.append(verdict_id)
        await self.connection.commit()
        return ids

    async def purge_expired_evidence(
        self, source: str, days: int, now: datetime | None = None
    ) -> list[str]:
        """Borra la evidencia de `source` no refrescada en `days` días.

        Lo exigen los términos de algunas plataformas (YouTube: refrescar o
        borrar en 30 días). Los duplicados que la apuntan caen en cascada.
        Devuelve los ids borrados, para purgar también sus vectores.
        """
        limite = (now or datetime.now(UTC)) - timedelta(days=days)
        filas = await self._fetchall(
            """
            DELETE FROM evidence_items
             WHERE tenant_id = %s AND source = %s AND fetched_at < %s
            RETURNING id
            """,
            (self.tenant_id, source, limite),
        )
        await self.connection.commit()
        return sorted(str(f["id"]) for f in filas)

    async def save_duplicates(self, duplicates: Sequence[Duplicate]) -> int:
        """Anota el crossposting (F2.6). Las dos filas ya deben estar guardadas."""
        for dup in duplicates:
            await self.connection.execute(
                """
                INSERT INTO evidence_duplicates (tenant_id, duplicate_id, canonical_id,
                                                 method, similarity)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, duplicate_id) DO UPDATE SET
                    canonical_id = EXCLUDED.canonical_id,
                    method = EXCLUDED.method,
                    similarity = EXCLUDED.similarity
                """,
                (self.tenant_id, dup.duplicate_id, dup.canonical_id, dup.method,
                 dup.similarity),
            )
        await self.connection.commit()
        return len(duplicates)

    @classmethod
    def from_env(cls) -> PostgresStore:
        return cls(dsn=resolver_dsn())

    # -- Ciclo de vida -----------------------------------------------------

    async def connect(self) -> None:
        if self._conn is not None:
            return

        import psycopg
        from psycopg.rows import dict_row

        self._conn = await psycopg.AsyncConnection.connect(
            self.dsn,
            row_factory=dict_row,
            options=SCHEMA_OPTIONS,
            autocommit=False,
        )

    async def aclose(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    @property
    def connection(self) -> AsyncConnection[dict[str, Any]]:
        if self._conn is None:
            raise RuntimeError("PostgresStore no está conectado: usa 'async with'.")
        return self._conn

    # -- Primitivas --------------------------------------------------------

    async def _fetchone_returning(
        self, sql: str, params: Sequence[Any] = ()
    ) -> dict[str, Any]:
        """
        Fila de un `INSERT ... RETURNING`, que siempre debe existir.

        Si no llega, algo va mal en el SQL o en la base: se falla aquí con un
        mensaje claro en lugar de indexar un `None` más adelante.
        """
        row = await self._fetchone(sql, params)
        if row is None:
            raise RuntimeError("La sentencia RETURNING no devolvió ninguna fila")
        return row

    async def _fetchone(self, sql: str, params: Sequence[Any] = ()) -> dict | None:
        async with self.connection.cursor() as cur:
            await cur.execute(sql, params)
            return await cur.fetchone()

    async def _fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[dict]:
        async with self.connection.cursor() as cur:
            await cur.execute(sql, params)
            return await cur.fetchall()

    # -- Ejecuciones -------------------------------------------------------

    async def start_run(
        self,
        subreddit_name: str,
        subreddit_id: str | None = None,
        trigger_source: str = "manual",
        parameters: dict[str, Any] | None = None,
        data_source: str | None = None,
    ) -> str:
        """
        Abre una ejecución y devuelve su identificador.

        `data_source` es "real" o "demo" en el escaneo multifuente; las filas
        antiguas conservan "reddit". None si quien persiste no lo sabe.
        """
        row = await self._fetchone_returning(
            """
            INSERT INTO pipeline_runs (tenant_id, subreddit_id, subreddit_name,
                                       trigger_source, parameters, status,
                                       data_source)
            VALUES (%s, %s, %s, %s, %s, 'running', %s)
            RETURNING id
            """,
            (
                self.tenant_id,
                subreddit_id,
                subreddit_name,
                trigger_source,
                json.dumps(parameters or {}),
                data_source,
            ),
        )
        await self.connection.commit()
        return str(row["id"])

    async def finish_run(
        self,
        run_id: str,
        stats: dict[str, int],
        errors: Sequence[str] = (),
        status: str = "completed",
        cycles: int = 0,
        last_cursor: str | None = None,
        top: dict[str, Any] | None = None,
    ) -> None:
        """
        Cierra la ejecución volcando sus contadores. Las columnas del Top N
        de la pipeline antigua (`top`) quedan en NULL si no se pasan: «no se
        calculó».
        """
        errors = list(errors or [])
        top = top or {}
        await self.connection.execute(
            """
            UPDATE pipeline_runs SET
                status       = %s,
                finished_at  = now(),
                duration_ms  = EXTRACT(EPOCH FROM (now() - started_at)) * 1000,
                cycles       = %s,
                fetched      = %s,
                filtered_in  = %s,
                filtered_out = %s,
                analyzed     = %s,
                stored       = %s,
                qualified    = %s,
                rejected     = %s,
                errors       = %s,
                error_count  = %s,
                last_cursor  = %s,
                top_n_target = %s,
                top_n_found  = %s,
                top_n_reason = %s
            WHERE id = %s AND tenant_id = %s
            """,
            (
                status,
                int(cycles),
                int(stats.get("fetched", 0)),
                int(stats.get("filtered_in", 0)),
                int(stats.get("filtered_out", 0)),
                int(stats.get("analyzed", 0)),
                int(stats.get("stored", 0)),
                int(stats.get("qualified", 0)),
                int(stats.get("rejected", 0)),
                json.dumps(errors),
                len(errors),
                last_cursor,
                top.get("target"),
                top.get("found"),
                top.get("reason"),
                run_id,
                self.tenant_id,
            ),
        )
        await self.connection.commit()
