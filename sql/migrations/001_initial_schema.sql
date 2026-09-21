-- =====================================================================
-- Reddit Intelligence Radar - Esquema relacional
-- =====================================================================
-- Destino: PostgreSQL 18+
-- Ejecución:  psql -h localhost -U postgres -d reddit_intelligence_radar -f sql/schema.sql
--
-- Notas de diseño
-- ---------------
-- 1. LOS EMBEDDINGS NO VIVEN AQUÍ. PostgreSQL guarda el rastro relacional,
--    inmutable y auditable; LanceDB guarda el espacio vectorial y resuelve
--    la búsqueda densa. `analyzed_signals.embedding_ref` es el puente entre
--    ambos. Esta separación es deliberada: pgvector no está disponible en la
--    instalación de destino, y aun estándolo, duplicar el índice vectorial
--    obligaría a mantener dos fuentes de verdad sincronizadas.
--
-- 2. MULTI-TENANT DESDE EL PRIMER DÍA. Añadir `tenant_id` más tarde obliga a
--    reescribir todos los índices y todas las consultas; llevarlo desde el
--    principio no estorba al uso local, donde basta con un único tenant
--    (`00000000-0000-0000-0000-000000000001`). Row Level Security queda
--    definida pero DESACTIVADA por defecto: se habilita en despliegue SaaS.
--
-- 3. CLAVES uuidv7(). Nativo en PostgreSQL 18. A diferencia de uuid v4, es
--    monótono en el tiempo, de modo que las inserciones caen al final del
--    índice B-Tree en lugar de fragmentarlo. Para PostgreSQL 13-17,
--    sustituir `uuidv7()` por `gen_random_uuid()`.
--
-- 4. IDENTIDAD DOBLE. Cada fila tiene una PK interna (uuid) y el
--    identificador de Reddit (`reddit_id`, p. ej. 't3_1abc23'). La segunda es
--    la clave natural para deduplicar entre ejecuciones; la primera es la que
--    referencian las claves foráneas.
-- =====================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS radar;
SET search_path = radar, public;

CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- búsqueda por similitud léxica
CREATE EXTENSION IF NOT EXISTS btree_gin;    -- índices GIN compuestos


-- =====================================================================
-- TIPOS ENUMERADOS
-- =====================================================================
-- Los valores replican exactamente lo que produce el motor de la Fase 3,
-- en forma de slug. La normalización de las etiquetas del clasificador
-- ('ready to buy' -> 'ready_to_buy') la hace el adaptador Python.

CREATE TYPE urgency_tier AS ENUM ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW');

CREATE TYPE buying_intent AS ENUM (
    'ready_to_buy',
    'seeking_recommendation',
    'seeking_alternative',
    'comparing_products',
    'casual_discussion',
    'none'
);

CREATE TYPE pain_severity AS ENUM (
    'severe_blocker',
    'time_consuming_friction',
    'minor_inconvenience',
    'no_problem',
    'none'
);

CREATE TYPE sentiment_label AS ENUM (
    'negative_frustration',
    'neutral_inquiry',
    'positive_praise',
    'unknown'
);

CREATE TYPE willingness_to_pay AS ENUM ('explicit', 'implicit', 'none');

CREATE TYPE urgency_level AS ENUM ('critical', 'high', 'medium', 'low');

CREATE TYPE signal_source AS ENUM ('post', 'comment');

CREATE TYPE subreddit_status AS ENUM ('active', 'paused', 'error', 'archived');

CREATE TYPE listing_sort AS ENUM ('hot', 'new', 'top', 'rising');

CREATE TYPE run_status AS ENUM ('running', 'completed', 'failed', 'cancelled');

-- Ciclo de vida de una oportunidad una vez llega a manos humanas.
CREATE TYPE validation_status AS ENUM (
    'new',
    'triaged',
    'validated',
    'rejected',
    'shipped'
);


-- =====================================================================
-- FUNCIÓN AUXILIAR: mantenimiento de updated_at
-- =====================================================================

CREATE OR REPLACE FUNCTION radar.touch_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;


-- =====================================================================
-- TENANTS
-- =====================================================================

CREATE TABLE tenants (
    id          uuid PRIMARY KEY DEFAULT uuidv7(),
    slug        text NOT NULL,
    name        text NOT NULL,
    settings    jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT tenants_slug_key UNIQUE (slug),
    CONSTRAINT tenants_slug_format CHECK (slug ~ '^[a-z0-9][a-z0-9_-]{1,62}$')
);

CREATE TRIGGER tenants_touch
    BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION radar.touch_updated_at();

-- Tenant por defecto para uso local en escritorio.
INSERT INTO tenants (id, slug, name)
VALUES ('00000000-0000-0000-0000-000000000001', 'local', 'Instalación local')
ON CONFLICT (slug) DO NOTHING;


-- =====================================================================
-- SUBREDDITS: configuración de monitoreo
-- =====================================================================

CREATE TABLE subreddits (
    id                      uuid PRIMARY KEY DEFAULT uuidv7(),
    tenant_id               uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    name                    text NOT NULL,              -- sin el prefijo 'r/'
    display_name            text,
    description             text,

    -- Parámetros de escaneo (espejo de los del grafo)
    listing                 listing_sort NOT NULL DEFAULT 'new',
    limit_per_page          smallint NOT NULL DEFAULT 25,
    max_cycles              smallint NOT NULL DEFAULT 5,
    target_qualified        smallint NOT NULL DEFAULT 10,
    min_opportunity_score   numeric(5,2) NOT NULL DEFAULT 60.00,
    max_age_days            smallint,

    -- Periodicidad
    scan_interval_minutes   integer NOT NULL DEFAULT 1440,
    last_scanned_at         timestamptz,
    next_scan_at            timestamptz,

    status                  subreddit_status NOT NULL DEFAULT 'active',
    last_error              text,
    consecutive_failures    smallint NOT NULL DEFAULT 0,

    config                  jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),

    -- Un subreddit es único por tenant, sin distinguir mayúsculas: r/SaaS
    -- y r/saas son el mismo sitio.
    CONSTRAINT subreddits_tenant_name_key UNIQUE (tenant_id, name),
    CONSTRAINT subreddits_name_format CHECK (name ~ '^[A-Za-z0-9_]{2,21}$'),
    CONSTRAINT subreddits_limit_range CHECK (limit_per_page BETWEEN 1 AND 100),
    CONSTRAINT subreddits_cycles_range CHECK (max_cycles BETWEEN 1 AND 100),
    CONSTRAINT subreddits_score_range CHECK (min_opportunity_score BETWEEN 0 AND 100),
    CONSTRAINT subreddits_interval_positive CHECK (scan_interval_minutes > 0)
);

CREATE TRIGGER subreddits_touch
    BEFORE UPDATE ON subreddits
    FOR EACH ROW EXECUTE FUNCTION radar.touch_updated_at();

-- Búsqueda case-insensitive por nombre.
CREATE UNIQUE INDEX subreddits_tenant_lower_name_idx
    ON subreddits (tenant_id, lower(name));

-- El planificador pregunta constantemente "¿qué toca escanear ahora?".
-- Índice parcial: solo los activos entran en esa cola.
CREATE INDEX subreddits_due_idx
    ON subreddits (next_scan_at ASC NULLS FIRST)
    WHERE status = 'active';

CREATE INDEX subreddits_tenant_status_idx ON subreddits (tenant_id, status);
CREATE INDEX subreddits_config_gin ON subreddits USING gin (config jsonb_path_ops);


-- =====================================================================
-- PIPELINE_RUNS: telemetría de cada ejecución del grafo
-- =====================================================================
-- Se crea al arrancar el grafo y se cierra al terminar. Es la tabla que
-- responde a "¿por qué el radar no encontró nada anoche?".

CREATE TABLE pipeline_runs (
    id                  uuid PRIMARY KEY DEFAULT uuidv7(),
    tenant_id           uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- SET NULL, no CASCADE: si se deja de monitorizar un subreddit, su
    -- historial de ejecuciones sigue siendo evidencia válida.
    subreddit_id        uuid REFERENCES subreddits(id) ON DELETE SET NULL,
    subreddit_name      text NOT NULL,      -- desnormalizado a propósito

    status              run_status NOT NULL DEFAULT 'running',
    trigger_source      text NOT NULL DEFAULT 'manual',  -- manual | schedule | mcp | api

    started_at          timestamptz NOT NULL DEFAULT now(),
    finished_at         timestamptz,
    duration_ms         integer,

    -- Contadores que emiten los nodos del grafo
    cycles              smallint NOT NULL DEFAULT 0,
    fetched             integer NOT NULL DEFAULT 0,
    filtered_in         integer NOT NULL DEFAULT 0,
    filtered_out        integer NOT NULL DEFAULT 0,
    analyzed            integer NOT NULL DEFAULT 0,
    stored              integer NOT NULL DEFAULT 0,
    qualified           integer NOT NULL DEFAULT 0,
    rejected            integer NOT NULL DEFAULT 0,

    -- Parámetros efectivos y errores no fatales de esta ejecución
    parameters          jsonb NOT NULL DEFAULT '{}'::jsonb,
    errors              jsonb NOT NULL DEFAULT '[]'::jsonb,
    error_count         integer NOT NULL DEFAULT 0,

    last_cursor         text,               -- cursor 'after' donde se quedó
    graph_version       text,
    created_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT pipeline_runs_finished_after_start
        CHECK (finished_at IS NULL OR finished_at >= started_at),
    CONSTRAINT pipeline_runs_counters_non_negative
        CHECK (fetched >= 0 AND analyzed >= 0 AND stored >= 0 AND qualified >= 0)
);

CREATE INDEX pipeline_runs_tenant_started_idx
    ON pipeline_runs (tenant_id, started_at DESC);

CREATE INDEX pipeline_runs_subreddit_started_idx
    ON pipeline_runs (subreddit_id, started_at DESC);

-- Para el panel de incidencias: ejecuciones vivas o fallidas.
CREATE INDEX pipeline_runs_unhealthy_idx
    ON pipeline_runs (tenant_id, started_at DESC)
    WHERE status IN ('running', 'failed');

CREATE INDEX pipeline_runs_errors_gin ON pipeline_runs USING gin (errors jsonb_path_ops);


-- =====================================================================
-- RAW_POSTS: contenido crudo, inmutable
-- =====================================================================
-- Inmutable por contrato: si Reddit cambia un post, entra una fila nueva
-- con otro content_hash. Nunca se reescribe el pasado, porque el análisis
-- que se hizo sobre él debe seguir siendo explicable.

CREATE TABLE raw_posts (
    id                  uuid PRIMARY KEY DEFAULT uuidv7(),
    tenant_id           uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    subreddit_id        uuid REFERENCES subreddits(id) ON DELETE SET NULL,
    run_id              uuid REFERENCES pipeline_runs(id) ON DELETE SET NULL,

    reddit_id           text NOT NULL,      -- 't3_1abc23'
    subreddit_name      text NOT NULL,

    title               text NOT NULL DEFAULT '',
    selftext            text NOT NULL DEFAULT '',
    author              text NOT NULL DEFAULT '[deleted]',

    -- Métricas de Reddit en el momento de la captura
    score               integer NOT NULL DEFAULT 0,
    upvote_ratio        numeric(4,3),
    num_comments        integer NOT NULL DEFAULT 0,

    created_utc         timestamptz NOT NULL,
    url                 text,
    permalink           text,
    flair               text,

    -- Veredicto del filtro léxico de la Fase 2
    is_pain_signal      boolean NOT NULL DEFAULT false,
    matched_keywords    text[] NOT NULL DEFAULT '{}',

    raw_payload         jsonb,              -- respuesta original de Reddit
    content_hash        text NOT NULL,      -- sha256(title || selftext)
    fetched_at          timestamptz NOT NULL DEFAULT now(),

    -- Deduplicación entre ejecuciones: el mismo post con el mismo contenido
    -- no se reinserta; si el contenido cambia, sí entra como versión nueva.
    CONSTRAINT raw_posts_tenant_reddit_hash_key
        UNIQUE (tenant_id, reddit_id, content_hash),
    CONSTRAINT raw_posts_upvote_ratio_range
        CHECK (upvote_ratio IS NULL OR upvote_ratio BETWEEN 0 AND 1)
);

CREATE INDEX raw_posts_tenant_created_idx ON raw_posts (tenant_id, created_utc DESC);
CREATE INDEX raw_posts_subreddit_created_idx ON raw_posts (subreddit_id, created_utc DESC);
CREATE INDEX raw_posts_reddit_id_idx ON raw_posts (tenant_id, reddit_id);
CREATE INDEX raw_posts_run_idx ON raw_posts (run_id);

-- Solo lo marcado como dolor alimenta el análisis: índice parcial.
CREATE INDEX raw_posts_pain_idx
    ON raw_posts (tenant_id, created_utc DESC)
    WHERE is_pain_signal;

-- Búsqueda full-text sobre título y cuerpo. La columna se genera sola, de
-- modo que no puede quedar desincronizada del contenido.
ALTER TABLE raw_posts
    ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(selftext, '')), 'B')
    ) STORED;

CREATE INDEX raw_posts_search_gin ON raw_posts USING gin (search_vector);
CREATE INDEX raw_posts_keywords_gin ON raw_posts USING gin (matched_keywords);
CREATE INDEX raw_posts_payload_gin ON raw_posts USING gin (raw_payload jsonb_path_ops);

-- Similitud léxica para nombres propios de herramientas ('pgpool', 'Stripe').
CREATE INDEX raw_posts_title_trgm ON raw_posts USING gin (title gin_trgm_ops);


-- =====================================================================
-- RAW_COMMENTS: contenido crudo de comentarios
-- =====================================================================

CREATE TABLE raw_comments (
    id                  uuid PRIMARY KEY DEFAULT uuidv7(),
    tenant_id           uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- CASCADE: un comentario sin su post no significa nada.
    post_id             uuid NOT NULL REFERENCES raw_posts(id) ON DELETE CASCADE,
    run_id              uuid REFERENCES pipeline_runs(id) ON DELETE SET NULL,

    reddit_id           text NOT NULL,      -- 't1_abc123'
    parent_reddit_id    text,

    author              text NOT NULL DEFAULT '[deleted]',
    body                text NOT NULL DEFAULT '',
    score               integer NOT NULL DEFAULT 0,
    created_utc         timestamptz NOT NULL,
    permalink           text,
    depth               smallint NOT NULL DEFAULT 0,

    is_pain_signal      boolean NOT NULL DEFAULT false,
    matched_keywords    text[] NOT NULL DEFAULT '{}',

    raw_payload         jsonb,
    content_hash        text NOT NULL,
    fetched_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT raw_comments_tenant_reddit_hash_key
        UNIQUE (tenant_id, reddit_id, content_hash)
);

CREATE INDEX raw_comments_post_created_idx ON raw_comments (post_id, created_utc DESC);
CREATE INDEX raw_comments_tenant_created_idx ON raw_comments (tenant_id, created_utc DESC);
CREATE INDEX raw_comments_parent_idx ON raw_comments (parent_reddit_id);

CREATE INDEX raw_comments_pain_idx
    ON raw_comments (tenant_id, created_utc DESC)
    WHERE is_pain_signal;

ALTER TABLE raw_comments
    ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(body, ''))) STORED;

CREATE INDEX raw_comments_search_gin ON raw_comments USING gin (search_vector);
CREATE INDEX raw_comments_keywords_gin ON raw_comments USING gin (matched_keywords);


-- =====================================================================
-- ANALYZED_SIGNALS: veredicto del motor de inteligencia
-- =====================================================================
-- Una fila por (señal, ejecución): analizar dos veces el mismo post en
-- momentos distintos produce puntuaciones distintas, porque el factor de
-- recencia decae. Conservar ambas permite ver cómo envejece una señal.

CREATE TABLE analyzed_signals (
    id                  uuid PRIMARY KEY DEFAULT uuidv7(),
    tenant_id           uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    run_id              uuid REFERENCES pipeline_runs(id) ON DELETE SET NULL,

    source_kind         signal_source NOT NULL,
    post_id             uuid REFERENCES raw_posts(id) ON DELETE CASCADE,
    comment_id          uuid REFERENCES raw_comments(id) ON DELETE CASCADE,

    reddit_id           text NOT NULL,
    subreddit_name      text NOT NULL,
    author              text NOT NULL DEFAULT '[deleted]',
    content             text NOT NULL,
    created_utc         timestamptz NOT NULL,

    -- Clasificación NLI zero-shot
    buying_intent       buying_intent NOT NULL DEFAULT 'none',
    intent_confidence   numeric(5,4) NOT NULL DEFAULT 0,
    pain_severity       pain_severity NOT NULL DEFAULT 'none',
    pain_confidence     numeric(5,4) NOT NULL DEFAULT 0,
    sentiment           sentiment_label NOT NULL DEFAULT 'unknown',

    -- ¿Vino de un modelo real o del fallback heurístico? Sin esto no se
    -- puede comparar una cosecha con otra tras habilitar transformers.
    classifier_engine   text NOT NULL DEFAULT 'heuristic',

    risk_flags          text[] NOT NULL DEFAULT '{}',

    -- Desglose del scoring temporal (cada factor en 0..1)
    spread_factor       numeric(5,4) NOT NULL DEFAULT 0,
    frequency_factor    numeric(5,4) NOT NULL DEFAULT 0,
    severity_factor     numeric(5,4) NOT NULL DEFAULT 0,
    recency_factor      numeric(5,4) NOT NULL DEFAULT 0,
    paid_signal_factor  numeric(5,4) NOT NULL DEFAULT 0,
    raw_score           numeric(6,3) NOT NULL DEFAULT 0,
    final_score         numeric(6,3) NOT NULL DEFAULT 0,
    urgency_tier        urgency_tier NOT NULL DEFAULT 'LOW',

    -- Métricas de agregación que alimentaron el scoring
    mention_count       integer NOT NULL DEFAULT 1,
    community_count     integer NOT NULL DEFAULT 1,
    average_severity    numeric(4,2),
    average_paid_signal numeric(4,2),
    newest_age_days     numeric(8,2),

    -- Puente con LanceDB: identificador del registro vectorial.
    embedding_ref       text,
    embedding_model     text,

    qualified           boolean NOT NULL DEFAULT false,
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    analyzed_at         timestamptz NOT NULL DEFAULT now(),

    -- Una señal procede de un post o de un comentario, nunca de ambos ni
    -- de ninguno.
    CONSTRAINT analyzed_signals_one_source CHECK (
        (source_kind = 'post'    AND post_id IS NOT NULL AND comment_id IS NULL) OR
        (source_kind = 'comment' AND comment_id IS NOT NULL AND post_id IS NULL)
    ),
    CONSTRAINT analyzed_signals_score_range CHECK (final_score BETWEEN 0 AND 100),
    CONSTRAINT analyzed_signals_factors_range CHECK (
        spread_factor BETWEEN 0 AND 1 AND
        frequency_factor BETWEEN 0 AND 1 AND
        severity_factor BETWEEN 0 AND 1 AND
        recency_factor BETWEEN 0 AND 1 AND
        paid_signal_factor BETWEEN 0 AND 1
    ),
    CONSTRAINT analyzed_signals_run_reddit_key UNIQUE (tenant_id, run_id, reddit_id)
);

CREATE INDEX analyzed_signals_tenant_score_idx
    ON analyzed_signals (tenant_id, final_score DESC, analyzed_at DESC);

CREATE INDEX analyzed_signals_tier_idx
    ON analyzed_signals (tenant_id, urgency_tier, final_score DESC);

CREATE INDEX analyzed_signals_created_idx
    ON analyzed_signals (tenant_id, created_utc DESC);

CREATE INDEX analyzed_signals_post_idx ON analyzed_signals (post_id);
CREATE INDEX analyzed_signals_comment_idx ON analyzed_signals (comment_id);
CREATE INDEX analyzed_signals_run_idx ON analyzed_signals (run_id);
CREATE INDEX analyzed_signals_embedding_ref_idx ON analyzed_signals (embedding_ref);

-- La consulta que hace el dashboard cada vez que se abre: lo cualificado,
-- limpio de riesgos, por orden de puntuación.
CREATE INDEX analyzed_signals_qualified_idx
    ON analyzed_signals (tenant_id, final_score DESC)
    WHERE qualified AND cardinality(risk_flags) = 0;

ALTER TABLE analyzed_signals
    ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED;

CREATE INDEX analyzed_signals_search_gin ON analyzed_signals USING gin (search_vector);
CREATE INDEX analyzed_signals_risks_gin ON analyzed_signals USING gin (risk_flags);
CREATE INDEX analyzed_signals_metadata_gin
    ON analyzed_signals USING gin (metadata jsonb_path_ops);


-- =====================================================================
-- JTBD_OPPORTUNITIES: síntesis accionable
-- =====================================================================
-- Aquí es donde el radar deja de describir Reddit y empieza a proponer
-- producto. Es la única tabla que edita un humano.

CREATE TABLE jtbd_opportunities (
    id                      uuid PRIMARY KEY DEFAULT uuidv7(),
    tenant_id               uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    signal_id               uuid NOT NULL REFERENCES analyzed_signals(id) ON DELETE CASCADE,

    -- Formulación Jobs-To-Be-Done
    job_statement           text NOT NULL,
    intent_type             text NOT NULL DEFAULT '',
    target_task             text NOT NULL DEFAULT '',
    friction_barrier        text NOT NULL DEFAULT '',

    -- Competencia y parches caseros
    current_solution        text,
    competitors_mentioned   text[] NOT NULL DEFAULT '{}',
    workaround_detected     boolean NOT NULL DEFAULT false,
    workaround_description  text,

    willingness_to_pay      willingness_to_pay NOT NULL DEFAULT 'none',
    urgency_level           urgency_level NOT NULL DEFAULT 'medium',
    risk_flags              text[] NOT NULL DEFAULT '{}',

    -- Citas literales del dolor, para la ficha de detalle del frontend
    evidence_quotes         jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_url              text,

    -- Ciclo de vida humano
    status                  validation_status NOT NULL DEFAULT 'new',
    assigned_to             text,
    validated_at            timestamptz,
    notes                   text,

    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),

    -- Una síntesis por señal: si se reanaliza, se actualiza, no se duplica.
    CONSTRAINT jtbd_signal_key UNIQUE (signal_id),
    CONSTRAINT jtbd_validated_has_timestamp CHECK (
        status <> 'validated' OR validated_at IS NOT NULL
    )
);

CREATE TRIGGER jtbd_touch
    BEFORE UPDATE ON jtbd_opportunities
    FOR EACH ROW EXECUTE FUNCTION radar.touch_updated_at();

CREATE INDEX jtbd_tenant_status_idx ON jtbd_opportunities (tenant_id, status, created_at DESC);
CREATE INDEX jtbd_urgency_idx ON jtbd_opportunities (tenant_id, urgency_level, created_at DESC);
CREATE INDEX jtbd_signal_idx ON jtbd_opportunities (signal_id);

-- La bandeja de trabajo: lo que aún nadie ha mirado.
CREATE INDEX jtbd_pending_idx
    ON jtbd_opportunities (tenant_id, created_at DESC)
    WHERE status IN ('new', 'triaged');

-- 'simple' y no 'english': el job statement se genera en español y los
-- nombres de herramientas no deben pasar por un stemmer inglés.
ALTER TABLE jtbd_opportunities
    ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(job_statement, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(current_solution, '')), 'B') ||
        setweight(to_tsvector('simple', coalesce(friction_barrier, '')), 'C')
    ) STORED;

CREATE INDEX jtbd_search_gin ON jtbd_opportunities USING gin (search_vector);
CREATE INDEX jtbd_competitors_gin ON jtbd_opportunities USING gin (competitors_mentioned);
CREATE INDEX jtbd_evidence_gin ON jtbd_opportunities USING gin (evidence_quotes jsonb_path_ops);


-- =====================================================================
-- VISTAS
-- =====================================================================

-- Alimenta el Radar View del frontend con una sola consulta.
CREATE VIEW v_radar_feed AS
SELECT
    s.id                AS signal_id,
    s.tenant_id,
    s.reddit_id,
    s.subreddit_name,
    s.author,
    s.content,
    s.created_utc,
    s.final_score,
    s.urgency_tier,
    s.buying_intent,
    s.pain_severity,
    s.sentiment,
    s.risk_flags,
    s.qualified,
    s.embedding_ref,
    j.id                AS opportunity_id,
    j.job_statement,
    j.current_solution,
    j.competitors_mentioned,
    j.workaround_detected,
    j.willingness_to_pay,
    j.status            AS validation_status,
    p.title             AS post_title,
    p.permalink         AS post_permalink,
    p.score             AS post_score,
    p.num_comments
FROM analyzed_signals s
LEFT JOIN jtbd_opportunities j ON j.signal_id = s.id
LEFT JOIN raw_posts p ON p.id = s.post_id;

COMMENT ON VIEW v_radar_feed IS
    'Feed unificado señal + síntesis JTBD + post original para el dashboard.';

-- Salud del pipeline: última ejecución de cada subreddit vigilado.
CREATE VIEW v_subreddit_health AS
SELECT DISTINCT ON (sr.id)
    sr.id               AS subreddit_id,
    sr.tenant_id,
    sr.name,
    sr.status,
    sr.last_scanned_at,
    sr.next_scan_at,
    sr.consecutive_failures,
    r.id                AS last_run_id,
    r.status            AS last_run_status,
    r.started_at        AS last_run_started_at,
    r.duration_ms       AS last_run_duration_ms,
    r.fetched,
    r.qualified,
    r.error_count
FROM subreddits sr
LEFT JOIN pipeline_runs r ON r.subreddit_id = sr.id
ORDER BY sr.id, r.started_at DESC NULLS LAST;

COMMENT ON VIEW v_subreddit_health IS
    'Estado de monitoreo y resultado de la última ejecución por subreddit.';


-- =====================================================================
-- ROW LEVEL SECURITY (definida, no activada)
-- =====================================================================
-- En despliegue SaaS, activar con:
--     ALTER TABLE radar.<tabla> ENABLE ROW LEVEL SECURITY;
-- y fijar el tenant al abrir cada conexión:
--     SET app.tenant_id = '<uuid>';
--
-- En instalación local no se activa: hay un único tenant y la comprobación
-- solo añadiría coste por fila.

CREATE POLICY tenant_isolation ON subreddits
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY tenant_isolation ON pipeline_runs
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY tenant_isolation ON raw_posts
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY tenant_isolation ON raw_comments
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY tenant_isolation ON analyzed_signals
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY tenant_isolation ON jtbd_opportunities
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);


-- =====================================================================
-- COMENTARIOS DE DOCUMENTACIÓN
-- =====================================================================

COMMENT ON SCHEMA radar IS
    'Reddit Intelligence Radar: rastro relacional. El espacio vectorial vive en LanceDB.';
COMMENT ON TABLE subreddits IS 'Configuración de monitoreo y periodicidad por subreddit.';
COMMENT ON TABLE pipeline_runs IS 'Telemetría y trazabilidad de cada ejecución del grafo LangGraph.';
COMMENT ON TABLE raw_posts IS 'Contenido crudo inmutable. Versionado por content_hash.';
COMMENT ON TABLE raw_comments IS 'Comentarios crudos inmutables, colgando de su post.';
COMMENT ON TABLE analyzed_signals IS 'Veredicto del motor: NLI, riesgos y desglose de scoring.';
COMMENT ON TABLE jtbd_opportunities IS 'Síntesis Jobs-To-Be-Done y su ciclo de validación humana.';
COMMENT ON COLUMN analyzed_signals.embedding_ref IS
    'Identificador del registro en LanceDB. Puente con el índice vectorial.';
COMMENT ON COLUMN analyzed_signals.classifier_engine IS
    'Motor que produjo la clasificación: "heuristic" o el modelo NLI empleado.';
COMMENT ON COLUMN raw_posts.content_hash IS
    'sha256(title || selftext). Permite versionar ediciones sin reescribir el pasado.';

COMMIT;
