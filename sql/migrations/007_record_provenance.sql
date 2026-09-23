-- =====================================================================
-- 007 - Fuente de los datos en cada registro (AUD-016, decision D-J)
-- =====================================================================
--
-- Hasta 006 solo la ejecucion sabia si sus datos eran de demostracion o de
-- Reddit (pipeline_runs.data_source). Las consultas que no pasan por ella
-- (el feed de senales, la salud por subreddit) mezclaban fuentes sin
-- decirlo. Cada registro persistido guarda ahora su propia fuente.
--
-- Las filas anteriores la heredan de su ejecucion. Si no tienen ejecucion,
-- o la ejecucion no la registro, queda NULL: la interfaz la muestra como
-- «desconocida», nunca se supone.
--
-- Las vistas ganan la columna al final: CREATE OR REPLACE VIEW solo admite
-- columnas nuevas detras de las que ya tenia.

BEGIN;

SET search_path = radar, public;

ALTER TABLE raw_posts
    ADD COLUMN data_source text CHECK (data_source IN ('demo', 'reddit'));
ALTER TABLE raw_comments
    ADD COLUMN data_source text CHECK (data_source IN ('demo', 'reddit'));
ALTER TABLE analyzed_signals
    ADD COLUMN data_source text CHECK (data_source IN ('demo', 'reddit'));

UPDATE raw_posts t SET data_source = r.data_source
  FROM pipeline_runs r
 WHERE t.run_id = r.id AND t.data_source IS NULL;
UPDATE raw_comments t SET data_source = r.data_source
  FROM pipeline_runs r
 WHERE t.run_id = r.id AND t.data_source IS NULL;
UPDATE analyzed_signals t SET data_source = r.data_source
  FROM pipeline_runs r
 WHERE t.run_id = r.id AND t.data_source IS NULL;

COMMENT ON COLUMN raw_posts.data_source IS
    'Fuente del post: demo o reddit; NULL = desconocida (anterior a D-J).';
COMMENT ON COLUMN raw_comments.data_source IS
    'Fuente del comentario: demo o reddit; NULL = desconocida (anterior a D-J).';
COMMENT ON COLUMN analyzed_signals.data_source IS
    'Fuente de la senal: demo o reddit; NULL = desconocida (anterior a D-J).';

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
    p.title             AS post_title,
    p.permalink         AS post_permalink,
    p.score             AS post_score,
    p.num_comments,
    s.data_source
FROM analyzed_signals s
LEFT JOIN jtbd_opportunities j ON j.signal_id = s.id
LEFT JOIN raw_posts p ON p.id = s.post_id;

CREATE OR REPLACE VIEW v_subreddit_health AS
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
    r.error_count,
    r.data_source       AS last_run_data_source
FROM subreddits sr
LEFT JOIN pipeline_runs r ON r.subreddit_id = sr.id
ORDER BY sr.id, r.started_at DESC NULLS LAST;

COMMIT;
