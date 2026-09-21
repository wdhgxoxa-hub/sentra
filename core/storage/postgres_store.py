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
from datetime import datetime, timezone
from typing import Any, Awaitable, Dict, List, Optional, Sequence, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def run_async(coro: Awaitable[T]) -> T:
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
}

_PAIN_SLUGS = {
    "severe blocker": "severe_blocker",
    "time consuming friction": "time_consuming_friction",
    "minor inconvenience": "minor_inconvenience",
    "no problem": "no_problem",
}

_SENTIMENT_SLUGS = {
    "negative frustration": "negative_frustration",
    "neutral inquiry": "neutral_inquiry",
    "positive praise": "positive_praise",
}

_WTP_VALUES = {"explicit", "implicit", "none"}
_URGENCY_LEVELS = {"critical", "high", "medium", "low"}


def _slugify(value: Optional[str]) -> str:
    return (value or "").strip().lower().replace(" ", "_")


def _normalize(value: Optional[str], table: Dict[str, str], fallback: str) -> str:
    """Traduce una etiqueta a su slug, aceptando que ya venga en forma de slug."""
    if not value:
        return fallback
    key = (value or "").strip().lower()
    if key in table:
        return table[key]
    slug = _slugify(value)
    return slug if slug in table.values() else fallback


def normalize_buying_intent(value: Optional[str]) -> str:
    return _normalize(value, _INTENT_SLUGS, "none")


def normalize_pain_severity(value: Optional[str]) -> str:
    return _normalize(value, _PAIN_SLUGS, "none")


def normalize_sentiment(value: Optional[str]) -> str:
    return _normalize(value, _SENTIMENT_SLUGS, "unknown")


def normalize_willingness_to_pay(value: Optional[str]) -> str:
    slug = _slugify(value)
    return slug if slug in _WTP_VALUES else "none"


def normalize_urgency_level(value: Optional[str]) -> str:
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
    payload = f"{title or ''}\x00{body or ''}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def to_timestamptz(epoch: Optional[float]) -> Optional[datetime]:
    """
    Convierte un `created_utc` de Reddit en datetime con zona.

    Un cero significa "sin dato", no el 1 de enero de 1970: devolver esa
    fecha contaminaría cualquier cálculo de antigüedad.
    """
    if not epoch:
        return None
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc)


def post_to_row(
    item: Dict[str, Any],
    subreddit_name: str,
    run_id: Optional[str] = None,
    subreddit_id: Optional[str] = None,
) -> Dict[str, Any]:
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
    }


def signal_to_row(
    signal: Any,
    run_id: Optional[str] = None,
    post_uuid: Optional[str] = None,
    comment_uuid: Optional[str] = None,
    qualified: bool = False,
    classifier_engine: str = "heuristic",
    embedding_ref: Optional[str] = None,
    embedding_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Traduce un `AnalyzedSignal` a una fila de `analyzed_signals`."""
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
        "classifier_engine": classifier_engine,
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
    }


def opportunity_to_row(signal: Any, signal_uuid: str) -> Dict[str, Any]:
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
        dsn: Optional[str] = None,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        self.dsn = dsn or os.environ.get(DSN_ENV_VAR) or DEFAULT_DSN
        self.tenant_id = tenant_id
        self._conn = None

    @classmethod
    def from_env(cls) -> "PostgresStore":
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

    async def __aenter__(self) -> "PostgresStore":
        await self.connect()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    @property
    def connection(self):
        if self._conn is None:
            raise RuntimeError("PostgresStore no está conectado: usa 'async with'.")
        return self._conn

    async def current_tenant_id(self) -> str:
        row = await self._fetchone(
            "SELECT id FROM tenants WHERE id = %s", (self.tenant_id,)
        )
        return str(row["id"]) if row else ""

    # -- Primitivas --------------------------------------------------------

    async def _fetchone(self, sql: str, params: Sequence[Any] = ()) -> Optional[Dict]:
        async with self.connection.cursor() as cur:
            await cur.execute(sql, params)
            return await cur.fetchone()

    async def _fetchall(self, sql: str, params: Sequence[Any] = ()) -> List[Dict]:
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

        row = await self._fetchone(
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
        subreddit_id: Optional[str] = None,
        trigger_source: str = "manual",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Abre una ejecución y devuelve su identificador."""
        row = await self._fetchone(
            """
            INSERT INTO pipeline_runs (tenant_id, subreddit_id, subreddit_name,
                                       trigger_source, parameters, status)
            VALUES (%s, %s, %s, %s, %s, 'running')
            RETURNING id
            """,
            (
                self.tenant_id,
                subreddit_id,
                subreddit_name,
                trigger_source,
                json.dumps(parameters or {}),
            ),
        )
        await self.connection.commit()
        return str(row["id"])

    async def finish_run(
        self,
        run_id: str,
        stats: Dict[str, int],
        errors: Sequence[str] = (),
        status: str = "completed",
        cycles: int = 0,
        last_cursor: Optional[str] = None,
    ) -> None:
        """Cierra la ejecución volcando los contadores que emitió el grafo."""
        errors = list(errors or [])
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
                last_cursor  = %s
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
                run_id,
                self.tenant_id,
            ),
        )
        await self.connection.commit()

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        return await self._fetchone(
            "SELECT * FROM pipeline_runs WHERE id = %s AND tenant_id = %s",
            (run_id, self.tenant_id),
        )

    # -- Contenido ---------------------------------------------------------

    async def save_raw_posts(
        self,
        items: Sequence[Dict[str, Any]],
        subreddit_name: str,
        subreddit_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Inserta posts crudos y devuelve el mapa `reddit_id -> uuid`.

        Un post ya visto con el mismo contenido no se reinserta; si cambió,
        entra como versión nueva (la clave incluye el hash del contenido).
        """
        saved: Dict[str, str] = {}

        for item in items:
            row = post_to_row(item, subreddit_name, run_id=run_id,
                              subreddit_id=subreddit_id)
            if not row["reddit_id"] or row["created_utc"] is None:
                logger.warning("Post sin id o sin fecha, se omite: %s", row["reddit_id"])
                continue

            result = await self._fetchone(
                """
                INSERT INTO raw_posts (tenant_id, subreddit_id, run_id, reddit_id,
                    subreddit_name, title, selftext, author, score, upvote_ratio,
                    num_comments, created_utc, url, permalink, flair,
                    is_pain_signal, matched_keywords, raw_payload, content_hash)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (tenant_id, reddit_id, content_hash) DO UPDATE
                    SET run_id = COALESCE(EXCLUDED.run_id, raw_posts.run_id)
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
                ),
            )
            saved[row["reddit_id"]] = str(result["id"])

        return saved

    async def save_signal(
        self,
        signal: Any,
        run_id: Optional[str] = None,
        post_uuid: Optional[str] = None,
        qualified: bool = False,
        classifier_engine: str = "heuristic",
        embedding_ref: Optional[str] = None,
        embedding_model: Optional[str] = None,
    ) -> Optional[str]:
        """Inserta el veredicto del motor y devuelve el id de la señal."""
        row = signal_to_row(
            signal, run_id=run_id, post_uuid=post_uuid, qualified=qualified,
            classifier_engine=classifier_engine,
            embedding_ref=embedding_ref or signal.id,
            embedding_model=embedding_model,
        )
        if row["created_utc"] is None or post_uuid is None:
            logger.warning("Señal sin post asociado o sin fecha: %s", row["reddit_id"])
            return None

        result = await self._fetchone(
            """
            INSERT INTO analyzed_signals (tenant_id, run_id, source_kind, post_id,
                reddit_id, subreddit_name, author, content, created_utc,
                buying_intent, intent_confidence, pain_severity, pain_confidence,
                sentiment, classifier_engine, risk_flags, spread_factor,
                frequency_factor, severity_factor, recency_factor,
                paid_signal_factor, raw_score, final_score, urgency_tier,
                mention_count, community_count, average_severity,
                average_paid_signal, newest_age_days, embedding_ref,
                embedding_model, qualified, metadata)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, run_id, reddit_id) DO UPDATE
                SET final_score = EXCLUDED.final_score,
                    qualified   = EXCLUDED.qualified
            RETURNING id
            """,
            (
                self.tenant_id, row["run_id"], row["source_kind"], row["post_id"],
                row["reddit_id"], row["subreddit_name"], row["author"],
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
            ),
        )
        return str(result["id"])

    async def save_opportunity(self, signal: Any, signal_uuid: str) -> str:
        """Inserta o actualiza la síntesis JTBD de una señal."""
        row = opportunity_to_row(signal, signal_uuid)
        result = await self._fetchone(
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

    # -- Puente con el grafo -----------------------------------------------

    async def persist_state(
        self,
        state: Dict[str, Any],
        trigger_source: str = "graph",
        classifier_engine: str = "heuristic",
        embedding_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Vuelca el estado final del grafo en una única transacción.

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
        )

        try:
            posts = await self.save_raw_posts(
                state.get("filtered_items") or [],
                subreddit_name,
                subreddit_id=subreddit_id,
                run_id=run_id,
            )

            signals_saved = 0
            opportunities_saved = 0

            for signal in state.get("signals") or []:
                signal_uuid = await self.save_signal(
                    signal,
                    run_id=run_id,
                    post_uuid=posts.get(signal.id),
                    qualified=signal.id in qualified_ids,
                    classifier_engine=classifier_engine,
                    embedding_model=embedding_model,
                )
                if signal_uuid is None:
                    continue
                signals_saved += 1

                await self.save_opportunity(signal, signal_uuid)
                opportunities_saved += 1

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
            cycles=int(state.get("cycle", 0)),
            last_cursor=state.get("cursor"),
        )

        return {
            "run_id": run_id,
            "subreddit_id": subreddit_id,
            "posts": len(posts),
            "signals": signals_saved,
            "opportunities": opportunities_saved,
        }

    # -- Consulta ----------------------------------------------------------

    async def fetch_radar_feed(
        self,
        limit: int = 50,
        min_score: float = 0.0,
        urgency_tiers: Optional[Sequence[str]] = None,
        subreddit_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Alimenta el Radar View: señales con su síntesis y su post original."""
        clauses = ["tenant_id = %s", "final_score >= %s"]
        params: List[Any] = [self.tenant_id, min_score]

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

    async def search_posts(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
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

    async def get_opportunity_detail(self, reddit_id: str) -> Optional[Dict[str, Any]]:
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
