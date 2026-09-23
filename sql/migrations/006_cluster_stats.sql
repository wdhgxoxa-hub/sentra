-- =====================================================================
-- 006 - Cifras exactas por problema para el PRD (AUD-009)
-- =====================================================================
--
-- El PRD afirmaba que la palabra principal «aparece en todas las quejas»
-- cuando `keywords` es una union de terminos. Cada problema guarda ahora sus
-- cifras exactas, calculadas sobre TODAS sus quejas
-- (core/orchestration/aggregation.py, cluster_stats):
--
--   mentions, distinct_texts, severity_undetermined,
--   keywords [{keyword, count}], pairs [{a, b, count}]
--
-- La vista del tablero las expone junto con la fuente de los datos de su
-- ejecucion, para que el PRD pueda declararla. CREATE OR REPLACE VIEW solo
-- admite columnas nuevas al final: las anteriores quedan igual que en 003.

BEGIN;

SET search_path = radar, public;

ALTER TABLE opportunity_clusters
    ADD COLUMN cluster_stats jsonb NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN opportunity_clusters.cluster_stats IS
    'Cifras exactas sobre todas las quejas del problema (AUD-009).';

CREATE OR REPLACE VIEW v_opportunity_board AS
SELECT
    c.id,
    c.tenant_id,
    c.cluster_key,
    c.label,
    c.intent_type,
    c.keywords,
    c.subreddits,
    c.mention_count,
    c.community_count,
    c.job_statement,
    c.current_solutions,
    c.risk_flags,
    c.spread_factor,
    c.frequency_factor,
    c.severity_factor,
    c.recency_factor,
    c.paid_signal_factor,
    c.final_score,
    c.urgency_tier,
    c.qualified,
    c.evidence,
    c.created_at,
    c.run_id,
    r.started_at              AS run_started_at,
    s.reddit_id               AS representative_reddit_id,
    s.content                 AS representative_content,
    (SELECT count(*) FROM opportunity_cluster_signals cs
      WHERE cs.cluster_id = c.id) AS linked_signals,
    COALESCE(v.status, 'new'::validation_status) AS validation_status,
    v.notes                   AS validation_notes,
    v.assigned_to             AS validation_assignee,
    v.validated_at            AS validated_at,
    c.cluster_stats,
    r.data_source
FROM opportunity_clusters c
LEFT JOIN pipeline_runs r ON r.id = c.run_id
LEFT JOIN analyzed_signals s ON s.id = c.representative_signal_id
LEFT JOIN cluster_validations v
       ON v.tenant_id = c.tenant_id AND v.cluster_key = c.cluster_key;

COMMIT;
