-- =====================================================================
-- 009 - Evidencia multifuente unificada (F2, decisiones D-M1 y D-M5)
-- =====================================================================
--
-- `evidence_items` es la tabla común de todas las fuentes: una fila por
-- pieza de evidencia, con id global '<fuente>:<id nativo>'. Las tablas
-- raw_posts, raw_comments y analyzed_signals se conservan pero ya no
-- reciben escrituras nuevas.
--
-- Copia de los datos anteriores con su procedencia, sin inferir nada
-- (D-M5): 'reddit' -> (reddit, real); 'demo' -> (demo, demo); NULL ->
-- (legacy, NULL = desconocida). Un NULL nunca cuenta como real.
--
-- R9: ningún nombre de usuario queda en claro. Los autores antiguos se
-- sustituyen por el HMAC-SHA256 que calcula core/evidence/author.py:
-- hmac(sal, '<fuente>:<autor en minúsculas>'). La sal NO está en este
-- archivo: la pone scripts/migrate.py en la sesión (rir.author_salt), y
-- solo hace falta si hay autores que hashear; una base nueva migra sin ella.

BEGIN;

SET search_path = radar, public;

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;

-- Temporal a propósito: depende de la sal de la sesión y no debe quedarse
-- en la base cuando la migración termine.
CREATE FUNCTION pg_temp.rir_author_hash(p_source text, p_author text) RETURNS text
LANGUAGE plpgsql AS $$
DECLARE
    nombre text := lower(btrim(coalesce(p_author, '')));
    sal text := coalesce(current_setting('rir.author_salt', true), '');
BEGIN
    IF nombre IN ('', '[deleted]', '[removed]', 'deleted', 'ghost') THEN
        RETURN NULL;
    END IF;
    IF sal = '' THEN
        RAISE EXCEPTION 'Hay autores antiguos que hashear y falta la sal (rir.author_salt): '
            'aplica la migración con scripts/migrate.py';
    END IF;
    RETURN encode(public.hmac(convert_to(p_source || ':' || nombre, 'UTF8'),
                              convert_to(sal, 'UTF8'), 'sha256'), 'hex');
END $$;

-- Fuente de un registro antiguo según su procedencia (D-M5).
CREATE FUNCTION pg_temp.rir_legacy_source(p_data_source text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE p_data_source WHEN 'reddit' THEN 'reddit' WHEN 'demo' THEN 'demo' ELSE 'legacy' END
$$;

-- --- Tablas -----------------------------------------------------------

CREATE TABLE evidence_items (
    id              text NOT NULL,                  -- '<fuente>:<id nativo>'
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    source          text NOT NULL,
    community       text NOT NULL,
    kind            text NOT NULL,
    title           text,
    content         text NOT NULL,
    url             text,
    author_hash     text,
    created_at      timestamptz NOT NULL,
    fetched_at      timestamptz NOT NULL,
    language        text,
    thread_id       text,
    score           integer,
    replies         integer,
    reactions       integer,
    views           integer,
    native_metrics  jsonb NOT NULL DEFAULT '{}'::jsonb,
    data_source     text,
    run_id          uuid REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    content_hash    text NOT NULL,
    -- De dónde salió la fila copiada (solo datos anteriores a esta migración).
    legacy_post_id    uuid,
    legacy_comment_id uuid,
    first_seen_at   timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (tenant_id, id),
    CONSTRAINT evidence_items_id_global CHECK (id LIKE source || ':_%'),
    CONSTRAINT evidence_items_kind CHECK (kind IN (
        'post', 'comment', 'question', 'answer', 'issue', 'discussion', 'review', 'product')),
    CONSTRAINT evidence_items_content_not_empty CHECK (btrim(content) <> ''),
    -- Atribución con enlace al original (R5). Solo un registro antiguo sin
    -- enlace guardado puede quedarse sin URL: no se inventa una.
    CONSTRAINT evidence_items_url CHECK (
        url LIKE 'https://%' OR (url IS NULL AND source = 'legacy')),
    CONSTRAINT evidence_items_author_hash CHECK (author_hash ~ '^[0-9a-f]{64}$'),
    -- NULL = procedencia desconocida (solo datos anteriores a D-J).
    CONSTRAINT evidence_items_data_source CHECK (data_source IN ('real', 'demo'))
);

CREATE INDEX evidence_items_source_idx ON evidence_items (tenant_id, source, created_at DESC);
CREATE INDEX evidence_items_community_idx ON evidence_items (tenant_id, source, community);
CREATE INDEX evidence_items_created_idx ON evidence_items (tenant_id, created_at DESC);
CREATE INDEX evidence_items_thread_idx ON evidence_items (tenant_id, thread_id);
CREATE INDEX evidence_items_run_idx ON evidence_items (run_id);
CREATE INDEX evidence_items_content_hash_idx ON evidence_items (tenant_id, content_hash);
CREATE INDEX evidence_items_legacy_post_idx ON evidence_items (legacy_post_id)
    WHERE legacy_post_id IS NOT NULL;

-- Crossposting: la misma pieza publicada en varias plataformas no es
-- corroboración (F2.6). Se conserva una y se anotan las demás.
CREATE TABLE evidence_duplicates (
    tenant_id     uuid NOT NULL,
    duplicate_id  text NOT NULL,
    canonical_id  text NOT NULL,
    method        text NOT NULL CHECK (method IN ('fingerprint', 'embedding')),
    similarity    numeric(5, 4),
    detected_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, duplicate_id),
    FOREIGN KEY (tenant_id, duplicate_id) REFERENCES evidence_items (tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, canonical_id) REFERENCES evidence_items (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT evidence_duplicates_not_self CHECK (duplicate_id <> canonical_id),
    CONSTRAINT evidence_duplicates_similarity CHECK (
        (method = 'fingerprint' AND similarity IS NULL)
        OR (method = 'embedding' AND similarity BETWEEN 0 AND 1))
);

-- Estado verificado de cada fuente (F2.4). Verde solo con una respuesta
-- real de la API: 'verificada' exige la hora de ese acceso.
CREATE TABLE sources_state (
    tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    source            text NOT NULL,
    status            text NOT NULL CHECK (status IN (
        'no_configurada', 'configurada_sin_verificar', 'verificada', 'error',
        'deshabilitada_por_usuario')),
    last_verified_at  timestamptz,
    error_code        text,
    detail            text,
    -- Aparte del estado: deshabilitar no borra lo último que dijo la API.
    disabled          boolean NOT NULL DEFAULT false,
    updated_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, source),
    CONSTRAINT sources_state_verified CHECK (status <> 'verificada' OR last_verified_at IS NOT NULL),
    CONSTRAINT sources_state_error CHECK (status <> 'error' OR error_code IS NOT NULL)
);

-- Una ejecución multifuente no es «reddit»: sus datos vienen de las APIs
-- de varias plataformas. 'real' es el mismo término que evidence_items.
ALTER TABLE pipeline_runs DROP CONSTRAINT pipeline_runs_data_source_check;
ALTER TABLE pipeline_runs ADD CONSTRAINT pipeline_runs_data_source_check
    CHECK (data_source IN ('demo', 'reddit', 'real'));
COMMENT ON COLUMN pipeline_runs.data_source IS
    'Fuente de los datos: demo (corpus fabricado), reddit (pipeline antigua) o real (escaneo multifuente).';

-- --- Copia de los datos anteriores (D-M5) -----------------------------

INSERT INTO evidence_items (
    id, tenant_id, source, community, kind, title, content, url, author_hash,
    created_at, fetched_at, thread_id, score, replies, native_metrics,
    data_source, run_id, content_hash, legacy_post_id)
SELECT DISTINCT ON (p.tenant_id, pg_temp.rir_legacy_source(p.data_source), p.reddit_id)
    pg_temp.rir_legacy_source(p.data_source) || ':' || p.reddit_id,
    p.tenant_id,
    pg_temp.rir_legacy_source(p.data_source),
    'r/' || p.subreddit_name,
    'post',
    nullif(p.title, ''),
    coalesce(nullif(btrim(p.selftext), ''), nullif(btrim(p.title), ''), '(sin texto)'),
    CASE WHEN p.permalink LIKE 'https://%' THEN p.permalink END,
    pg_temp.rir_author_hash(pg_temp.rir_legacy_source(p.data_source), p.author),
    p.created_utc,
    p.fetched_at,
    pg_temp.rir_legacy_source(p.data_source) || ':' || p.reddit_id,
    p.score,
    p.num_comments,
    jsonb_strip_nulls(jsonb_build_object('upvote_ratio', p.upvote_ratio, 'flair', p.flair)),
    CASE p.data_source WHEN 'reddit' THEN 'real' WHEN 'demo' THEN 'demo' END,
    p.run_id,
    p.content_hash,
    p.id
FROM raw_posts p
ORDER BY p.tenant_id, pg_temp.rir_legacy_source(p.data_source), p.reddit_id, p.fetched_at DESC;

INSERT INTO evidence_items (
    id, tenant_id, source, community, kind, content, url, author_hash,
    created_at, fetched_at, thread_id, score, native_metrics,
    data_source, run_id, content_hash, legacy_comment_id)
SELECT DISTINCT ON (c.tenant_id, pg_temp.rir_legacy_source(c.data_source), c.reddit_id)
    pg_temp.rir_legacy_source(c.data_source) || ':' || c.reddit_id,
    c.tenant_id,
    pg_temp.rir_legacy_source(c.data_source),
    'r/' || p.subreddit_name,
    'comment',
    coalesce(nullif(btrim(c.body), ''), '(sin texto)'),
    CASE WHEN c.permalink LIKE 'https://%' THEN c.permalink END,
    pg_temp.rir_author_hash(pg_temp.rir_legacy_source(c.data_source), c.author),
    c.created_utc,
    c.fetched_at,
    pg_temp.rir_legacy_source(p.data_source) || ':' || p.reddit_id,
    c.score,
    jsonb_build_object('depth', c.depth),
    CASE c.data_source WHEN 'reddit' THEN 'real' WHEN 'demo' THEN 'demo' END,
    c.run_id,
    c.content_hash,
    c.id
FROM raw_comments c
JOIN raw_posts p ON p.id = c.post_id
-- Sin URL solo se admite en la fuente 'legacy': un comentario de Reddit o
-- demo sin enlace no se puede atribuir y no se copia.
WHERE c.permalink LIKE 'https://%' OR pg_temp.rir_legacy_source(c.data_source) = 'legacy'
ORDER BY c.tenant_id, pg_temp.rir_legacy_source(c.data_source), c.reddit_id, c.fetched_at DESC;

-- --- Autores antiguos: hash en lugar del nombre (R9) --------------------

UPDATE raw_posts SET author =
    coalesce(pg_temp.rir_author_hash(pg_temp.rir_legacy_source(data_source), author), '[deleted]');
UPDATE raw_comments SET author =
    coalesce(pg_temp.rir_author_hash(pg_temp.rir_legacy_source(data_source), author), '[deleted]');
UPDATE analyzed_signals SET author =
    coalesce(pg_temp.rir_author_hash(pg_temp.rir_legacy_source(data_source), author), '[deleted]');

-- La carga cruda de la API (raw_payload) repetía el autor en claro. Se
-- quitan esas claves; el resto de la carga se conserva.
UPDATE raw_posts SET raw_payload = raw_payload - 'author' - 'author_fullname'
WHERE raw_payload ?| ARRAY['author', 'author_fullname'];
UPDATE raw_comments SET raw_payload = raw_payload - 'author' - 'author_fullname'
WHERE raw_payload ?| ARRAY['author', 'author_fullname'];

-- Las citas de cada cluster guardaban el autor dentro del JSON.
UPDATE opportunity_clusters c SET evidence = (
    SELECT jsonb_agg(
        CASE WHEN e ? 'author' THEN jsonb_set(e, '{author}', to_jsonb(coalesce(
            pg_temp.rir_author_hash(pg_temp.rir_legacy_source(r.data_source), e->>'author'),
            '[deleted]')))
        ELSE e END ORDER BY ord)
    FROM jsonb_array_elements(c.evidence) WITH ORDINALITY AS t(e, ord)
)
FROM pipeline_runs r
WHERE r.id = c.run_id AND jsonb_typeof(c.evidence) = 'array' AND c.evidence::text LIKE '%"author"%';

UPDATE opportunity_clusters c SET evidence = (
    SELECT jsonb_agg(
        CASE WHEN e ? 'author' THEN jsonb_set(e, '{author}', to_jsonb(coalesce(
            pg_temp.rir_author_hash('legacy', e->>'author'), '[deleted]')))
        ELSE e END ORDER BY ord)
    FROM jsonb_array_elements(c.evidence) WITH ORDINALITY AS t(e, ord)
)
WHERE c.run_id IS NULL AND jsonb_typeof(c.evidence) = 'array' AND c.evidence::text LIKE '%"author"%';

-- --- La vista del feed lee título, enlace e interacción de evidence_items ---

CREATE OR REPLACE VIEW v_radar_feed AS
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
    e.title             AS post_title,
    e.url               AS post_permalink,
    e.score             AS post_score,
    e.replies           AS num_comments,
    s.data_source
FROM analyzed_signals s
LEFT JOIN jtbd_opportunities j ON j.signal_id = s.id
LEFT JOIN evidence_items e ON e.tenant_id = s.tenant_id AND e.legacy_post_id = s.post_id;

-- --- Row level security (definida, no activada - ver migración 001) ----

CREATE POLICY tenant_isolation ON evidence_items
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY tenant_isolation ON evidence_duplicates
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY tenant_isolation ON sources_state
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMENT ON TABLE evidence_items IS
    'Evidencia de todas las fuentes. id global <fuente>:<id nativo>; autor solo como hash salado (R9).';
COMMENT ON COLUMN evidence_items.data_source IS
    'real (API de una plataforma) o demo; NULL = procedencia desconocida (datos anteriores a D-J).';
COMMENT ON TABLE evidence_duplicates IS
    'Crossposting: la misma pieza en varias plataformas no es corroboración.';
COMMENT ON TABLE sources_state IS
    'Estado verificado de cada fuente: verde solo con una respuesta real de la API.';

COMMIT;
