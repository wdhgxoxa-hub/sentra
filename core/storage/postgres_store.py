"""
Adaptador PostgreSQL (Fase 6)
=============================

Persiste en PostgreSQL el resultado de los nodos del grafo, complementando
a LanceDB en lugar de sustituirlo:

- **LanceDB** guarda el espacio vectorial y resuelve la búsqueda densa.
- **PostgreSQL** guarda el rastro relacional: qué se leyó, qué se descartó,
  con qué puntuación, en qué ejecución y por qué. Es lo que permite auditar
  una cosecha meses después y lo que alimenta al frontend.

El puente entre ambos es `analyzed_signals.embedding_ref`, que guarda el
identificador del registro en LanceDB.

Las funciones de mapeo (`post_to_row`, `signal_to_row`, los normalizadores)
son puras a propósito: la traducción entre el dominio y el esquema se puede
verificar sin levantar una base de datos.

Uso:

    async with PostgresStore() as store:
        resumen = await store.persist_state(estado_final_del_grafo)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
import uuid
from collections.abc import Coroutine, Sequence
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Self

from core.evidence.author import AuthorSaltMissing, author_hash, es_autor_identificable
from core.evidence.model import EvidenceItem, content_fingerprint

from .identity import Candidato, Previo, asignar_identidades

if TYPE_CHECKING:
    from psycopg import AsyncConnection

    from core.sources.dedup import Duplicate

logger = logging.getLogger(__name__)

def _fuente(data_source: str | None) -> str:
    """Fuente de un registro de la pipeline de Reddit según su procedencia (D-M5)."""
    return {"reddit": "reddit", "demo": "demo"}.get(data_source or "", "legacy")


def _procedencia(data_source: str | None) -> str | None:
    """'reddit' es dato real; 'demo', de demostración; lo demás, desconocido."""
    return {"reddit": "real", "demo": "demo"}.get(data_source or "")


#: Claves de la carga cruda de la API que llevan el nombre del autor (R9).
_CLAVES_DE_AUTOR = ("author", "author_fullname")


def _sin_autor(carga: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in carga.items() if k not in _CLAVES_DE_AUTOR}


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

# Tenant de la instalación local (ver sql/schema.sql).
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"

DEFAULT_DSN = (
    "host=localhost port=5432 user=postgres dbname=reddit_intelligence_radar"
)
DSN_ENV_VAR = "RIR_PG_DSN"

# El adaptador fija el search_path en la conexión, no por sentencia: así
# sobrevive a los rollbacks, que revierten cualquier SET hecho dentro de
# la transacción.
SCHEMA_OPTIONS = "-c search_path=radar,public"


# =====================================================================
# Normalización de etiquetas a los ENUM del esquema
# =====================================================================
# El clasificador produce etiquetas legibles con espacios ('ready to buy');
# el esquema usa slugs. La traducción vive aquí, en un único sitio.

_INTENT_SLUGS = {
    "ready to buy": "ready_to_buy",
    "seeking recommendation": "seeking_recommendation",
    "seeking alternative": "seeking_alternative",
    "comparing products": "comparing_products",
    "casual discussion": "casual_discussion",
    "undetermined": "undetermined",
}

_PAIN_SLUGS = {
    "severe blocker": "severe_blocker",
    "time consuming friction": "time_consuming_friction",
    "minor inconvenience": "minor_inconvenience",
    "no problem": "no_problem",
    "undetermined": "undetermined",
}

_SENTIMENT_SLUGS = {
    "negative frustration": "negative_frustration",
    "neutral inquiry": "neutral_inquiry",
    "positive praise": "positive_praise",
    "undetermined": "undetermined",
}

_WTP_VALUES = {"explicit", "implicit", "none"}
_URGENCY_LEVELS = {"critical", "high", "medium", "low"}


def _slugify(value: str | None) -> str:
    return (value or "").strip().lower().replace(" ", "_")


def _normalize(value: str | None, table: dict[str, str], fallback: str) -> str:
    """Traduce una etiqueta a su slug, aceptando que ya venga en forma de slug."""
    if not value:
        return fallback
    key = (value or "").strip().lower()
    if key in table:
        return table[key]
    slug = _slugify(value)
    return slug if slug in table.values() else fallback


def normalize_buying_intent(value: str | None) -> str:
    return _normalize(value, _INTENT_SLUGS, "none")


def normalize_pain_severity(value: str | None) -> str:
    return _normalize(value, _PAIN_SLUGS, "none")


def normalize_sentiment(value: str | None) -> str:
    return _normalize(value, _SENTIMENT_SLUGS, "unknown")


def normalize_willingness_to_pay(value: str | None) -> str:
    slug = _slugify(value)
    return slug if slug in _WTP_VALUES else "none"


def normalize_urgency_level(value: str | None) -> str:
    slug = _slugify(value)
    return slug if slug in _URGENCY_LEVELS else "medium"


# =====================================================================
# Utilidades de mapeo
# =====================================================================

def compute_content_hash(title: str, body: str) -> str:
    """
    Huella del contenido, para versionar ediciones sin pisar el pasado.

    El separador nulo evita que ('ab', '') y ('a', 'b') colisionen.
    """
    payload = f"{title or ''}\x00{body or ''}".encode()
    return hashlib.sha256(payload).hexdigest()


def to_timestamptz(epoch: float | None) -> datetime | None:
    """
    Convierte un `created_utc` de Reddit en datetime con zona.

    Un cero significa "sin dato", no el 1 de enero de 1970: devolver esa
    fecha contaminaría cualquier cálculo de antigüedad.
    """
    if not epoch:
        return None
    return datetime.fromtimestamp(float(epoch), tz=UTC)


def post_to_row(
    item: dict[str, Any],
    subreddit_name: str,
    run_id: str | None = None,
    subreddit_id: str | None = None,
    data_source: str | None = None,
) -> dict[str, Any]:
    """Traduce un post normalizado de la Fase 2 a una fila de `raw_posts`."""
    title = str(item.get("title") or "")
    selftext = str(item.get("selftext") or item.get("body") or "")

    return {
        "subreddit_id": subreddit_id,
        "run_id": run_id,
        "reddit_id": str(item.get("id") or ""),
        "subreddit_name": str(item.get("subreddit") or subreddit_name),
        "title": title,
        "selftext": selftext,
        "author": str(item.get("author") or "[deleted]"),
        "score": int(item.get("score") or 0),
        "upvote_ratio": item.get("upvote_ratio"),
        "num_comments": int(item.get("num_comments") or 0),
        "created_utc": to_timestamptz(item.get("created_utc")),
        "url": item.get("url"),
        "permalink": item.get("permalink"),
        "flair": item.get("flair"),
        "is_pain_signal": bool(item.get("is_pain_signal", False)),
        "matched_keywords": list(item.get("matched_keywords") or []),
        "raw_payload": dict(item),
        "content_hash": compute_content_hash(title, selftext),
        "data_source": data_source,
    }


def signal_to_row(
    signal: Any,
    run_id: str | None = None,
    post_uuid: str | None = None,
    comment_uuid: str | None = None,
    qualified: bool = False,
    classifier_engine: str | None = None,
    embedding_ref: str | None = None,
    embedding_model: str | None = None,
    data_source: str | None = None,
) -> dict[str, Any]:
    """
    Traduce un `AnalyzedSignal` a una fila de `analyzed_signals`.

    `classifier_engine` sale por defecto de la propia señal, que sabe qué
    motor la clasificó de verdad (AUD-005).
    """
    breakdown = signal.score_breakdown
    metrics = signal.temporal_metrics

    return {
        "run_id": run_id,
        "source_kind": "comment" if comment_uuid else "post",
        "post_id": post_uuid,
        "comment_id": comment_uuid,
        "reddit_id": signal.id,
        "subreddit_name": signal.subreddit,
        "author": signal.author or "[deleted]",
        "content": signal.text,
        "created_utc": to_timestamptz(signal.created_utc),
        "buying_intent": normalize_buying_intent(signal.buying_intent),
        "intent_confidence": float(signal.intent_confidence or 0.0),
        "pain_severity": normalize_pain_severity(signal.pain_severity),
        "pain_confidence": float(signal.pain_confidence or 0.0),
        "sentiment": normalize_sentiment(signal.sentiment),
        "classifier_engine": classifier_engine or signal.classifier_engine,
        "risk_flags": list(signal.jtbd.risk_flags or []),
        "spread_factor": breakdown.spread_factor,
        "frequency_factor": breakdown.frequency_factor,
        "severity_factor": breakdown.severity_factor,
        "recency_factor": breakdown.recency_factor,
        "paid_signal_factor": breakdown.paid_signal_factor,
        "raw_score": breakdown.raw_score,
        "final_score": breakdown.final_score,
        "urgency_tier": breakdown.urgency_tier,
        "mention_count": int(getattr(metrics, "mention_count", 1) or 1),
        "community_count": int(getattr(metrics, "community_count", 1) or 1),
        "average_severity": getattr(metrics, "average_severity", None),
        "average_paid_signal": getattr(metrics, "average_paid_signal", None),
        "newest_age_days": getattr(metrics, "newest_age_days", None),
        "embedding_ref": embedding_ref,
        "embedding_model": embedding_model,
        "qualified": bool(qualified),
        "metadata": {},
        "data_source": data_source,
    }


def cluster_to_row(cluster: dict[str, Any], qualified: bool = False) -> dict[str, Any]:
    """
    Traduce un cluster agregado a una fila de `opportunity_clusters`.

    El desglose del scoring se aplana en columnas en lugar de guardarse como
    JSON: son cinco números que el frontend pinta en cada ficha y sobre los
    que se querrá ordenar y filtrar.
    """
    breakdown = cluster.get("score_breakdown") or {}

    return {
        "cluster_key": cluster.get("key", ""),
        "label": cluster.get("label", ""),
        "intent_type": cluster.get("intent_type", ""),
        "keywords": list(cluster.get("keywords") or []),
        "subreddits": list(cluster.get("subreddits") or []),
        "mention_count": int(cluster.get("mention_count", 0)),
        "community_count": int(cluster.get("community_count", 0)),
        "representative_reddit_id": cluster.get("representative_id"),
        "job_statement": cluster.get("job_statement", ""),
        "current_solutions": list(cluster.get("current_solutions") or []),
        "risk_flags": list(cluster.get("risk_flags") or []),
        "spread_factor": breakdown.get("spread_factor", 0.0),
        "frequency_factor": breakdown.get("frequency_factor", 0.0),
        "severity_factor": breakdown.get("severity_factor", 0.0),
        "recency_factor": breakdown.get("recency_factor", 0.0),
        "paid_signal_factor": breakdown.get("paid_signal_factor", 0.0),
        "raw_score": breakdown.get("raw_score", 0.0),
        "final_score": cluster.get("opportunity_score", 0.0),
        "urgency_tier": cluster.get("urgency_tier", "LOW"),
        "qualified": bool(qualified),
        "evidence": list(cluster.get("evidence") or []),
        "signal_ids": list(cluster.get("signal_ids") or []),
        # Posición en el Top N de la ejecución, o None (AUD-007).
        "top_rank": cluster.get("top_rank"),
        # Cifras exactas por palabra y por texto (AUD-009).
        "cluster_stats": dict(cluster.get("stats") or {}),
    }


def opportunity_to_row(signal: Any, signal_uuid: str) -> dict[str, Any]:
    """Traduce la parte JTBD de una señal a una fila de `jtbd_opportunities`."""
    jtbd = signal.jtbd
    competitors = [jtbd.current_solution] if jtbd.current_solution else []

    return {
        "signal_id": signal_uuid,
        "job_statement": jtbd.job_statement or "",
        "intent_type": jtbd.intent_type or "",
        "target_task": jtbd.target_task or "",
        "friction_barrier": jtbd.friction_barrier or "",
        "current_solution": jtbd.current_solution,
        "competitors_mentioned": competitors,
        "workaround_detected": bool(jtbd.workaround_detected),
        "workaround_description": jtbd.workaround_description,
        "willingness_to_pay": normalize_willingness_to_pay(jtbd.willingness_to_pay),
        "urgency_level": normalize_urgency_level(jtbd.urgency_level),
        "risk_flags": list(jtbd.risk_flags or []),
        "evidence_quotes": [{"quote": signal.text[:500], "source": jtbd.source_url}],
        "source_url": jtbd.source_url,
    }


def _cosecha(state: dict[str, Any], acumulada: str, de_la_pagina: str) -> list[Any]:
    """
    Lo que se persiste: la cosecha de TODOS los ciclos (AUD-006).

    `filtered_items` y `signals` son solo la página en curso y se reemplazan
    en cada vuelta del grafo. La clave de página solo se usa si el estado no
    trae la acumulada, como el que se construye a mano fuera del grafo.
    """
    if acumulada in state:
        return list(state[acumulada] or [])
    return list(state.get(de_la_pagina) or [])


# =====================================================================
# Repositorio
# =====================================================================

class PostgresStore:
    """
    Repositorio asíncrono sobre el esquema `radar`.

    Abre una conexión propia y la mantiene mientras viva el contexto:

        async with PostgresStore() as store:
            await store.persist_state(state)
    """

    def __init__(
        self,
        dsn: str | None = None,
        tenant_id: str = DEFAULT_TENANT_ID,
        author_salt: str | None = None,
    ) -> None:
        self.dsn = dsn or os.environ.get(DSN_ENV_VAR) or DEFAULT_DSN
        self.tenant_id = tenant_id
        # R9: sin sal no se guarda ningún autor (ver AuthorSaltMissing).
        self._author_salt = author_salt
        self._conn: AsyncConnection[dict[str, Any]] | None = None

    # -- Autores y evidencia (R9, D-M1) ------------------------------------

    def _hash_autor(self, fuente: str, nombre: Any) -> str | None:
        """Hash salado del autor, o None si no hay autor identificable."""
        if not es_autor_identificable(str(nombre or "")):
            return None
        if not self._author_salt:
            raise AuthorSaltMissing(
                "Hay autores que guardar y PostgresStore no tiene sal (author_salt)."
            )
        return author_hash(fuente, str(nombre), self._author_salt)

    def _autor(self, fuente: str, nombre: Any) -> str:
        """El autor tal como se guarda en las tablas antiguas: hash o '[deleted]'."""
        return self._hash_autor(fuente, nombre) or "[deleted]"

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

    async def _guardar_evidencia(
        self,
        *,
        fuente: str,
        nativo: str,
        community: str,
        kind: str,
        title: str | None,
        content: str,
        url: Any,
        author: Any,
        created: datetime,
        run_id: str | None,
        data_source: str | None,
        content_hash: str,
        thread_id: str,
        score: int,
        replies: int | None,
        legacy_post_id: str | None = None,
        legacy_comment_id: str | None = None,
    ) -> None:
        """Upsert de la pieza en evidence_items (la tabla común de F2).

        La pipeline de Reddit sigue escribiendo sus tablas antiguas mientras
        el escaneo multifuente no la sustituya; esta copia es la que leen
        las vistas.
        """
        enlace = str(url) if isinstance(url, str) and url.startswith("https://") else None
        if enlace is None and fuente == "reddit":
            # URL canónica oficial de Reddit para un post o comentario por id.
            enlace = f"https://www.reddit.com/comments/{nativo.removeprefix('t3_')}"
        if enlace is None and fuente != "legacy":
            logger.warning("Evidencia sin enlace atribuible, no se guarda: %s:%s", fuente, nativo)
            return
        texto = content.strip() or (title or "").strip() or "(sin texto)"
        await self.connection.execute(
            """
            INSERT INTO evidence_items (id, tenant_id, source, community, kind, title,
                content, url, author_hash, created_at, fetched_at, thread_id, score,
                replies, data_source, run_id, content_hash, legacy_post_id,
                legacy_comment_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, id) DO UPDATE SET
                title = EXCLUDED.title,
                content = EXCLUDED.content,
                content_hash = EXCLUDED.content_hash,
                score = EXCLUDED.score,
                replies = EXCLUDED.replies,
                fetched_at = EXCLUDED.fetched_at,
                run_id = COALESCE(EXCLUDED.run_id, evidence_items.run_id),
                data_source = COALESCE(evidence_items.data_source, EXCLUDED.data_source),
                legacy_post_id = COALESCE(EXCLUDED.legacy_post_id, evidence_items.legacy_post_id),
                legacy_comment_id = COALESCE(EXCLUDED.legacy_comment_id,
                                             evidence_items.legacy_comment_id)
            """,
            (
                f"{fuente}:{nativo}", self.tenant_id, fuente, community, kind,
                title or None, texto, enlace,
                self._hash_autor(fuente, author),
                created, thread_id, score, replies, _procedencia(data_source), run_id,
                content_hash, legacy_post_id, legacy_comment_id,
            ),
        )

    @classmethod
    def from_env(cls) -> PostgresStore:
        return cls(dsn=os.environ.get(DSN_ENV_VAR))

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

    async def current_tenant_id(self) -> str:
        row = await self._fetchone(
            "SELECT id FROM tenants WHERE id = %s", (self.tenant_id,)
        )
        return str(row["id"]) if row else ""

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

    # -- Subreddits --------------------------------------------------------

    async def ensure_subreddit(self, name: str, **config: Any) -> str:
        """
        Devuelve el id del subreddit, creándolo si hace falta.

        Idempotente: la clave natural es (tenant, nombre).
        """
        clean = name.strip().removeprefix("r/").removeprefix("/")

        row = await self._fetchone(
            "SELECT id FROM subreddits WHERE tenant_id = %s AND lower(name) = lower(%s)",
            (self.tenant_id, clean),
        )
        if row:
            return str(row["id"])

        row = await self._fetchone_returning(
            """
            INSERT INTO subreddits (tenant_id, name, listing, limit_per_page,
                                    min_opportunity_score, config)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                self.tenant_id,
                clean,
                config.get("listing", "new"),
                config.get("limit_per_page", 25),
                config.get("min_opportunity_score", 60.0),
                json.dumps(config.get("config", {})),
            ),
        )
        await self.connection.commit()
        return str(row["id"])

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

        `data_source` es "demo", "reddit" (pipeline antigua) o "real"
        (escaneo multifuente); None si quien persiste no lo sabe.
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
        Cierra la ejecución volcando los contadores que emitió el grafo.

        `top` es el resultado Top N del grafo (`top_n.run_outcome`); sin él
        las columnas quedan en NULL, que significa «no se calculó».
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

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        return await self._fetchone(
            "SELECT * FROM pipeline_runs WHERE id = %s AND tenant_id = %s",
            (run_id, self.tenant_id),
        )

    # -- Contenido ---------------------------------------------------------

    async def save_raw_posts(
        self,
        items: Sequence[dict[str, Any]],
        subreddit_name: str,
        subreddit_id: str | None = None,
        run_id: str | None = None,
        data_source: str | None = None,
    ) -> dict[str, str]:
        """
        Inserta posts crudos y devuelve el mapa `reddit_id -> uuid`.

        Un post ya visto con el mismo contenido no se reinserta; si cambió,
        entra como versión nueva (la clave incluye el hash del contenido).
        """
        saved: dict[str, str] = {}

        for item in items:
            row = post_to_row(item, subreddit_name, run_id=run_id,
                              subreddit_id=subreddit_id, data_source=data_source)
            if not row["reddit_id"] or row["created_utc"] is None:
                logger.warning("Post sin id o sin fecha, se omite: %s", row["reddit_id"])
                continue
            fuente = _fuente(data_source)
            nombre = row["author"]
            row["author"] = self._autor(fuente, nombre)
            row["raw_payload"] = _sin_autor(row["raw_payload"])

            result = await self._fetchone_returning(
                """
                INSERT INTO raw_posts (tenant_id, subreddit_id, run_id, reddit_id,
                    subreddit_name, title, selftext, author, score, upvote_ratio,
                    num_comments, created_utc, url, permalink, flair,
                    is_pain_signal, matched_keywords, raw_payload, content_hash,
                    data_source)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (tenant_id, reddit_id, content_hash) DO UPDATE
                    SET run_id = COALESCE(EXCLUDED.run_id, raw_posts.run_id),
                        -- La fuente de un post ya guardado no cambia; solo
                        -- se completa si era desconocida.
                        data_source = COALESCE(raw_posts.data_source,
                                               EXCLUDED.data_source)
                RETURNING id
                """,
                (
                    self.tenant_id, row["subreddit_id"], row["run_id"],
                    row["reddit_id"], row["subreddit_name"], row["title"],
                    row["selftext"], row["author"], row["score"],
                    row["upvote_ratio"], row["num_comments"], row["created_utc"],
                    row["url"], row["permalink"], row["flair"],
                    row["is_pain_signal"], row["matched_keywords"],
                    json.dumps(row["raw_payload"], default=str), row["content_hash"],
                    row["data_source"],
                ),
            )
            saved[row["reddit_id"]] = str(result["id"])
            await self._guardar_evidencia(
                fuente=fuente, nativo=row["reddit_id"], community=f"r/{row['subreddit_name']}",
                kind="post", title=row["title"], content=row["selftext"],
                url=row["permalink"], author=nombre, created=row["created_utc"],
                run_id=run_id, data_source=data_source, content_hash=row["content_hash"],
                thread_id=f"{fuente}:{row['reddit_id']}", score=row["score"],
                replies=row["num_comments"], legacy_post_id=saved[row["reddit_id"]],
            )

        return saved

    async def save_raw_comments(
        self,
        comments: Sequence[dict[str, Any]],
        post_uuids: dict[str, str],
        run_id: str | None = None,
        data_source: str | None = None,
    ) -> dict[str, str]:
        """
        Inserta comentarios crudos (D-I) y devuelve el mapa `reddit_id -> uuid`.

        Cada uno cuelga de su post, que tiene que estar ya guardado: un
        comentario sin post no significa nada (y la tabla lo exige).
        """
        saved: dict[str, str] = {}
        for comment in comments:
            reddit_id = str(comment.get("id") or "")
            post_uuid = post_uuids.get(str(comment.get("post_id") or ""))
            created = to_timestamptz(comment.get("created_utc"))
            if not reddit_id or post_uuid is None or created is None:
                logger.warning("Comentario sin post guardado o sin fecha, se omite: %s", reddit_id)
                continue
            body = str(comment.get("body") or "")
            fuente = _fuente(data_source)
            nombre = comment.get("author")
            result = await self._fetchone_returning(
                """
                INSERT INTO raw_comments (tenant_id, post_id, run_id, reddit_id,
                    parent_reddit_id, author, body, score, created_utc, permalink,
                    depth, is_pain_signal, matched_keywords, raw_payload, content_hash,
                    data_source)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (tenant_id, reddit_id, content_hash) DO UPDATE
                    SET run_id = COALESCE(EXCLUDED.run_id, raw_comments.run_id),
                        data_source = COALESCE(raw_comments.data_source,
                                               EXCLUDED.data_source)
                RETURNING id
                """,
                (
                    self.tenant_id, post_uuid, run_id, reddit_id,
                    comment.get("parent_id"),
                    self._autor(fuente, nombre), body,
                    int(comment.get("score") or 0), created, comment.get("permalink"),
                    int(comment.get("depth") or 0),
                    bool(comment.get("is_pain_signal", False)),
                    list(comment.get("matched_keywords") or []),
                    json.dumps(_sin_autor(dict(comment)), default=str),
                    compute_content_hash("", body), data_source,
                ),
            )
            saved[reddit_id] = str(result["id"])
            post_id = str(comment.get("post_id") or "")
            await self._guardar_evidencia(
                fuente=fuente, nativo=reddit_id,
                community=f"r/{comment.get('subreddit') or ''}".rstrip("/") or "r/",
                kind="comment", title=None, content=body, url=comment.get("permalink"),
                author=nombre, created=created, run_id=run_id, data_source=data_source,
                content_hash=compute_content_hash("", body),
                thread_id=f"{fuente}:{post_id}", score=int(comment.get("score") or 0),
                replies=None, legacy_comment_id=saved[reddit_id],
            )
        return saved

    async def save_signal(
        self,
        signal: Any,
        run_id: str | None = None,
        post_uuid: str | None = None,
        qualified: bool = False,
        classifier_engine: str | None = None,
        embedding_ref: str | None = None,
        embedding_model: str | None = None,
        data_source: str | None = None,
        comment_uuid: str | None = None,
    ) -> str | None:
        """Inserta el veredicto del motor y devuelve el id de la señal.

        Con `comment_uuid` la señal es de un comentario (source_kind
        'comment') y va sin `post_uuid`: su post se alcanza por raw_comments
        (la tabla exige una sola fuente por señal).
        """
        row = signal_to_row(
            signal, run_id=run_id, post_uuid=post_uuid, comment_uuid=comment_uuid,
            qualified=qualified,
            classifier_engine=classifier_engine,
            embedding_ref=embedding_ref or signal.id,
            embedding_model=embedding_model,
            data_source=data_source,
        )
        if row["created_utc"] is None or (post_uuid is None and comment_uuid is None):
            logger.warning("Señal sin post ni comentario asociado, o sin fecha: %s",
                           row["reddit_id"])
            return None
        row["author"] = self._autor(_fuente(data_source), row["author"])

        result = await self._fetchone_returning(
            """
            INSERT INTO analyzed_signals (tenant_id, run_id, source_kind, post_id,
                comment_id, reddit_id, subreddit_name, author, content, created_utc,
                buying_intent, intent_confidence, pain_severity, pain_confidence,
                sentiment, classifier_engine, risk_flags, spread_factor,
                frequency_factor, severity_factor, recency_factor,
                paid_signal_factor, raw_score, final_score, urgency_tier,
                mention_count, community_count, average_severity,
                average_paid_signal, newest_age_days, embedding_ref,
                embedding_model, qualified, metadata, data_source)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, run_id, reddit_id) DO UPDATE
                SET final_score = EXCLUDED.final_score,
                    qualified   = EXCLUDED.qualified
            RETURNING id
            """,
            (
                self.tenant_id, row["run_id"], row["source_kind"], row["post_id"],
                row["comment_id"], row["reddit_id"], row["subreddit_name"], row["author"],
                row["content"], row["created_utc"], row["buying_intent"],
                row["intent_confidence"], row["pain_severity"],
                row["pain_confidence"], row["sentiment"], row["classifier_engine"],
                row["risk_flags"], row["spread_factor"], row["frequency_factor"],
                row["severity_factor"], row["recency_factor"],
                row["paid_signal_factor"], row["raw_score"], row["final_score"],
                row["urgency_tier"], row["mention_count"], row["community_count"],
                row["average_severity"], row["average_paid_signal"],
                row["newest_age_days"], row["embedding_ref"],
                row["embedding_model"], row["qualified"],
                json.dumps(row["metadata"]),
                row["data_source"],
            ),
        )
        return str(result["id"])

    async def save_opportunity(self, signal: Any, signal_uuid: str) -> str:
        """Inserta o actualiza la síntesis JTBD de una señal."""
        row = opportunity_to_row(signal, signal_uuid)
        result = await self._fetchone_returning(
            """
            INSERT INTO jtbd_opportunities (tenant_id, signal_id, job_statement,
                intent_type, target_task, friction_barrier, current_solution,
                competitors_mentioned, workaround_detected, workaround_description,
                willingness_to_pay, urgency_level, risk_flags, evidence_quotes,
                source_url)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (signal_id) DO UPDATE
                SET job_statement    = EXCLUDED.job_statement,
                    current_solution = EXCLUDED.current_solution,
                    updated_at       = now()
            RETURNING id
            """,
            (
                self.tenant_id, row["signal_id"], row["job_statement"],
                row["intent_type"], row["target_task"], row["friction_barrier"],
                row["current_solution"], row["competitors_mentioned"],
                row["workaround_detected"], row["workaround_description"],
                row["willingness_to_pay"], row["urgency_level"], row["risk_flags"],
                json.dumps(row["evidence_quotes"], default=str), row["source_url"],
            ),
        )
        return str(result["id"])

    async def fetch_opportunity_identities(self) -> list[Previo]:
        """Última lectura de cada oportunidad: sus señales y sus palabras (D-G)."""
        rows = await self._fetchall(
            """
            SELECT DISTINCT ON (c.opportunity_id)
                   c.opportunity_id::text AS opportunity_id,
                   c.keywords,
                   ARRAY(SELECT s.reddit_id
                           FROM opportunity_cluster_signals cs
                           JOIN analyzed_signals s ON s.id = cs.signal_id
                          WHERE cs.cluster_id = c.id) AS members
            FROM opportunity_clusters c
            WHERE c.tenant_id = %s
            ORDER BY c.opportunity_id, c.created_at DESC
            """,
            (self.tenant_id,),
        )
        return [
            Previo(str(r["opportunity_id"]), set(r["members"] or []), set(r["keywords"] or []))
            for r in rows
        ]

    async def assign_opportunity_ids(
        self, clusters: Sequence[dict[str, Any]]
    ) -> dict[str, str]:
        """UUID de cada cluster: heredado de una oportunidad anterior o nuevo (D-G)."""
        candidatos = [
            Candidato(
                str(c.get("key") or ""),
                {str(i) for i in c.get("signal_ids") or []},
                {str(k) for k in c.get("keywords") or []},
            )
            for c in clusters
        ]
        heredados = asignar_identidades(candidatos, await self.fetch_opportunity_identities())
        return {clave: uid or str(uuid.uuid4()) for clave, uid in heredados.items()}

    async def save_cluster(
        self,
        cluster: dict[str, Any],
        run_id: str | None,
        signal_uuids: dict[str, str],
        qualified: bool = False,
        opportunity_id: str | None = None,
        data_source: str | None = None,
    ) -> str | None:
        """
        Inserta un cluster y lo enlaza con las señales que lo sostienen.

        `opportunity_id` es su identidad estable (D-G); sin ella se le asigna
        una nueva, como a una oportunidad que aparece por primera vez.

        `signal_uuids` mapea el identificador de Reddit al uuid de la señal
        ya persistida. Las señales que no estén ahí (por ejemplo, de una
        ejecución anterior) se omiten del enlace: la fila del cluster
        conserva el recuento correcto de todos modos.
        """
        row = cluster_to_row(cluster, qualified=qualified)
        if not row["cluster_key"]:
            logger.warning("Cluster sin clave, se omite")
            return None
        fuente = _fuente(data_source)
        row["evidence"] = [
            {**cita, "author": self._autor(fuente, cita["author"])} if "author" in cita else cita
            for cita in row["evidence"]
        ]

        representative_uuid = signal_uuids.get(row["representative_reddit_id"] or "")

        result = await self._fetchone_returning(
            """
            INSERT INTO opportunity_clusters (tenant_id, run_id, cluster_key, label,
                intent_type, keywords, subreddits, mention_count, community_count,
                representative_signal_id, representative_reddit_id, job_statement,
                current_solutions, risk_flags, spread_factor, frequency_factor,
                severity_factor, recency_factor, paid_signal_factor, raw_score,
                final_score, urgency_tier, qualified, evidence, top_rank,
                cluster_stats, opportunity_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, run_id, cluster_key) DO UPDATE
                SET final_score = EXCLUDED.final_score,
                    qualified   = EXCLUDED.qualified,
                    top_rank    = EXCLUDED.top_rank,
                    cluster_stats = EXCLUDED.cluster_stats,
                    updated_at  = now()
            RETURNING id
            """,
            (
                self.tenant_id, run_id, row["cluster_key"], row["label"],
                row["intent_type"], row["keywords"], row["subreddits"],
                row["mention_count"], row["community_count"],
                representative_uuid, row["representative_reddit_id"],
                row["job_statement"], row["current_solutions"], row["risk_flags"],
                row["spread_factor"], row["frequency_factor"],
                row["severity_factor"], row["recency_factor"],
                row["paid_signal_factor"], row["raw_score"], row["final_score"],
                row["urgency_tier"], row["qualified"],
                json.dumps(row["evidence"], default=str),
                row["top_rank"],
                json.dumps(row["cluster_stats"]),
                opportunity_id or str(uuid.uuid4()),
            ),
        )
        cluster_id = str(result["id"])

        for reddit_id in row["signal_ids"]:
            signal_uuid = signal_uuids.get(reddit_id)
            if not signal_uuid:
                continue
            await self.connection.execute(
                """
                INSERT INTO opportunity_cluster_signals
                    (cluster_id, signal_id, tenant_id, is_representative)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (cluster_id, signal_id) DO NOTHING
                """,
                (
                    cluster_id,
                    signal_uuid,
                    self.tenant_id,
                    signal_uuid == representative_uuid,
                ),
            )

        return cluster_id

    # -- Puente con el grafo -----------------------------------------------

    async def persist_state(
        self,
        state: dict[str, Any],
        trigger_source: str = "graph",
        classifier_engine: str | None = None,
        embedding_model: str | None = None,
        status: str = "completed",
        data_source: str | None = None,
    ) -> dict[str, Any]:
        """
        Vuelca el estado final del grafo en una única transacción.

        `data_source` ("demo" o "reddit") queda en la ejecución (AUD-007) y en
        cada post y señal que escribe (D-J); el resultado Top N
        (`state["top"]`), en la ejecución.

        Escribe, en orden: subreddit, ejecución, posts crudos, señales
        analizadas y síntesis JTBD. Si algo falla, no queda media cosecha
        a medio escribir.
        """
        subreddit_name = str(state.get("subreddit") or "")
        qualified_ids = {q.get("id") for q in (state.get("qualified") or [])}

        subreddit_id = await self.ensure_subreddit(subreddit_name)
        run_id = await self.start_run(
            subreddit_name,
            subreddit_id=subreddit_id,
            trigger_source=trigger_source,
            parameters={"limit": state.get("limit"), "sort": state.get("sort")},
            data_source=data_source,
        )

        try:
            posts = await self.save_raw_posts(
                _cosecha(state, "all_items", "filtered_items"),
                subreddit_name,
                subreddit_id=subreddit_id,
                run_id=run_id,
                data_source=data_source,
            )

            # Comentarios (D-I): todos los traídos, colgando de su post.
            comentarios = list(state.get("all_comments") or [])
            comment_uuids = await self.save_raw_comments(
                comentarios, posts, run_id=run_id, data_source=data_source
            )

            signals_saved = 0
            opportunities_saved = 0
            signal_uuids: dict[str, str] = {}

            for signal in _cosecha(state, "all_signals", "signals"):
                es_comentario = signal.id in comment_uuids
                signal_uuid = await self.save_signal(
                    signal,
                    run_id=run_id,
                    post_uuid=None if es_comentario else posts.get(signal.id),
                    comment_uuid=comment_uuids.get(signal.id),
                    qualified=signal.id in qualified_ids,
                    classifier_engine=classifier_engine,
                    embedding_model=embedding_model,
                    data_source=data_source,
                )
                if signal_uuid is None:
                    continue
                signals_saved += 1
                signal_uuids[signal.id] = signal_uuid

                await self.save_opportunity(signal, signal_uuid)
                opportunities_saved += 1

            # Los clusters van después de las señales: necesitan sus uuid
            # para poblar la tabla pivote.
            qualified_keys = {
                c.get("key") for c in (state.get("qualified_clusters") or [])
            }
            clusters = list(state.get("clusters") or [])
            identidades = await self.assign_opportunity_ids(clusters)
            clusters_saved = 0
            for cluster in clusters:
                saved = await self.save_cluster(
                    cluster,
                    run_id=run_id,
                    signal_uuids=signal_uuids,
                    qualified=cluster.get("key") in qualified_keys,
                    opportunity_id=identidades.get(str(cluster.get("key") or "")),
                    data_source=data_source,
                )
                if saved:
                    clusters_saved += 1

            await self.connection.commit()
        except Exception:
            await self.connection.rollback()
            await self.finish_run(run_id, stats={}, errors=["persistencia fallida"],
                                  status="failed")
            raise

        await self.finish_run(
            run_id,
            stats=state.get("stats") or {},
            errors=state.get("errors") or [],
            status=status,
            cycles=int(state.get("cycle", 0)),
            last_cursor=state.get("cursor"),
            top=state.get("top"),
        )

        return {
            "run_id": run_id,
            "subreddit_id": subreddit_id,
            "posts": len(posts),
            "comments": len(comment_uuids),
            "signals": signals_saved,
            "opportunities": opportunities_saved,
            "clusters": clusters_saved,
        }

    async def fetch_opportunity_board(
        self,
        limit: int = 50,
        min_score: float = 0.0,
        qualified_only: bool = False,
        urgency_tiers: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Alimenta el tablero de oportunidades consolidadas del frontend."""
        clauses = ["tenant_id = %s", "final_score >= %s"]
        params: list[Any] = [self.tenant_id, min_score]

        if qualified_only:
            clauses.append("qualified")
        if urgency_tiers:
            clauses.append("urgency_tier = ANY(%s)")
            params.append(list(urgency_tiers))

        params.append(limit)
        return await self._fetchall(
            f"""
            SELECT * FROM v_opportunity_board
            WHERE {' AND '.join(clauses)}
            ORDER BY final_score DESC, created_at DESC
            LIMIT %s
            """,
            params,
        )

    async def fetch_cluster_history(
        self,
        cluster_key: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Lecturas sucesivas de un mismo problema, de la más reciente atrás.

        Es lo que permite ver que un dolor pasó de 2 a 9 comunidades: ese
        movimiento vale más que la foto fija.
        """
        return await self._fetchall(
            """
            SELECT id, run_id, final_score, urgency_tier, mention_count,
                   community_count, qualified, created_at
            FROM opportunity_clusters
            WHERE tenant_id = %s AND cluster_key = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (self.tenant_id, cluster_key, limit),
        )

    # -- Consulta ----------------------------------------------------------

    async def fetch_radar_feed(
        self,
        limit: int = 50,
        min_score: float = 0.0,
        urgency_tiers: Sequence[str] | None = None,
        subreddit_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Alimenta el Radar View: señales con su síntesis y su post original."""
        clauses = ["tenant_id = %s", "final_score >= %s"]
        params: list[Any] = [self.tenant_id, min_score]

        if urgency_tiers:
            clauses.append("urgency_tier = ANY(%s)")
            params.append(list(urgency_tiers))
        if subreddit_name:
            clauses.append("lower(subreddit_name) = lower(%s)")
            params.append(subreddit_name)

        params.append(limit)
        return await self._fetchall(
            f"""
            SELECT * FROM v_radar_feed
            WHERE {' AND '.join(clauses)}
            ORDER BY final_score DESC, created_utc DESC
            LIMIT %s
            """,
            params,
        )

    async def search_posts(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Búsqueda full-text sobre el contenido crudo, ordenada por relevancia."""
        return await self._fetchall(
            """
            SELECT reddit_id, title, selftext, author, score, created_utc,
                   ts_rank(search_vector, websearch_to_tsquery('english', %s)) AS rank
            FROM raw_posts
            WHERE tenant_id = %s
              AND search_vector @@ websearch_to_tsquery('english', %s)
            ORDER BY rank DESC, created_utc DESC
            LIMIT %s
            """,
            (query, self.tenant_id, query, limit),
        )

    async def get_opportunity_detail(self, reddit_id: str) -> dict[str, Any] | None:
        """Ficha completa para el Deep-Dive del frontend."""
        return await self._fetchone(
            """
            SELECT * FROM v_radar_feed
            WHERE tenant_id = %s AND reddit_id = %s
            ORDER BY final_score DESC
            LIMIT 1
            """,
            (self.tenant_id, reddit_id),
        )

    async def count_posts(self) -> int:
        row = await self._fetchone(
            "SELECT count(*) AS n FROM raw_posts WHERE tenant_id = %s",
            (self.tenant_id,),
        )
        return int(row["n"]) if row else 0
