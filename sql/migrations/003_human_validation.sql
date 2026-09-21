-- =====================================================================
-- 003 - Ciclo de validación humana (deuda D17)
-- =====================================================================
-- Hasta ahora el radar describía Reddit pero nadie podía anotar qué hacer
-- con lo que encontraba. Esta migración añade el juicio humano.
--
-- La decisión que ordena el resto: **la validación va por `cluster_key`,
-- no por fila de `opportunity_clusters`**. Esa tabla guarda una lectura por
-- ejecución (ver migración 002), así que validar una fila sería validar una
-- foto. Lo que un analista valida es el PROBLEMA, que sobrevive a cada
-- escaneo y cuya puntuación cambia con el tiempo.
--
-- Consecuencia práctica: marcar una oportunidad como "validada" hoy sigue
-- valiendo cuando mañana entre una lectura nueva con más menciones.
-- =====================================================================

BEGIN;

SET search_path = radar, public;


-- =====================================================================
-- CLUSTER_VALIDATIONS
-- =====================================================================

CREATE TABLE cluster_validations (
    tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Clave natural del problema, no una FK a una lectura concreta: las
    -- lecturas van y vienen, el problema permanece.
    cluster_key   text NOT NULL,

    status        validation_status NOT NULL DEFAULT 'new',
    notes         text,
    assigned_to   text,

    -- Se rellena al pasar a 'validated' y se conserva aunque luego cambie
    -- de estado: interesa saber cuándo se tomó la decisión.
    validated_at  timestamptz,

    -- Última lectura vista al emitir el juicio. Permite detectar que el
    -- problema ha crecido mucho desde que alguien lo descartó.
    score_at_decision numeric(6,3),

    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (tenant_id, cluster_key),
    CONSTRAINT cluster_validations_validated_has_timestamp CHECK (
        status <> 'validated' OR validated_at IS NOT NULL
    )
);

CREATE TRIGGER cluster_validations_touch
    BEFORE UPDATE ON cluster_validations
    FOR EACH ROW EXECUTE FUNCTION radar.touch_updated_at();

-- La bandeja de trabajo: lo que nadie ha mirado o está en curso.
CREATE INDEX cluster_validations_pending_idx
    ON cluster_validations (tenant_id, updated_at DESC)
    WHERE status IN ('new', 'triaged');

CREATE INDEX cluster_validations_status_idx
    ON cluster_validations (tenant_id, status, updated_at DESC);

CREATE INDEX cluster_validations_assignee_idx
    ON cluster_validations (tenant_id, assigned_to)
    WHERE assigned_to IS NOT NULL;

CREATE POLICY tenant_isolation ON cluster_validations
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMENT ON TABLE cluster_validations IS
    'Juicio humano sobre un problema recurrente. Va por cluster_key porque las lecturas cambian y el problema no.';


-- =====================================================================
-- SUBREDDITS: etiquetas de organización
-- =====================================================================
-- Vigilar veinte subreddits sin poder agruparlos los vuelve una lista
-- plana e inmanejable.

ALTER TABLE subreddits
    ADD COLUMN tags text[] NOT NULL DEFAULT '{}';

CREATE INDEX subreddits_tags_gin ON subreddits USING gin (tags);

COMMENT ON COLUMN subreddits.tags IS
    'Etiquetas libres para agrupar subreddits vigilados (vertical, idioma, prioridad...).';


-- =====================================================================
-- VISTA: el tablero incluye ahora el estado de validación
-- =====================================================================
-- LEFT JOIN a propósito: un problema sin validar no debe desaparecer del
-- tablero, que es justo donde alguien tiene que verlo para validarlo.

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
    v.validated_at            AS validated_at
FROM opportunity_clusters c
LEFT JOIN pipeline_runs r ON r.id = c.run_id
LEFT JOIN analyzed_signals s ON s.id = c.representative_signal_id
LEFT JOIN cluster_validations v
       ON v.tenant_id = c.tenant_id AND v.cluster_key = c.cluster_key;

COMMENT ON VIEW v_opportunity_board IS
    'Tablero de oportunidades consolidadas, con su estado de validación humana.';

COMMIT;
