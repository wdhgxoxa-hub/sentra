-- =====================================================================
-- 002 - Persistencia de clusters de oportunidad (deuda D12)
-- =====================================================================
-- Hasta ahora `aggregation_node` consolidaba los problemas recurrentes en
-- memoria y el resultado moría con el proceso. Eso obligaba al frontend a
-- recalcular los clusters en cada consulta y, peor, impedía ver cómo
-- evoluciona una oportunidad entre ejecuciones: si un dolor pasó de 2 a 9
-- comunidades en un mes, ese movimiento ES la señal.
--
-- Se guarda UNA FILA POR (ejecución, cluster), igual que `analyzed_signals`
-- guarda una fila por (ejecución, señal). No se actualiza el cluster
-- anterior: se añade su nueva lectura. La clave natural `cluster_key`
-- permite seguir el mismo problema a lo largo del tiempo.
--
-- La relación con las señales es N:M y no una columna de array porque hace
-- falta poder preguntar en ambas direcciones: "qué señales sostienen esta
-- oportunidad" y "en qué oportunidades aparece esta queja".
-- =====================================================================

BEGIN;

SET search_path = radar, public;


-- =====================================================================
-- OPPORTUNITY_CLUSTERS
-- =====================================================================

CREATE TABLE opportunity_clusters (
    id                       uuid PRIMARY KEY DEFAULT uuidv7(),
    tenant_id                uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- SET NULL: purgar telemetría antigua no debe borrar la oportunidad.
    run_id                   uuid REFERENCES pipeline_runs(id) ON DELETE SET NULL,

    -- Clave natural del problema, estable entre ejecuciones. Es lo que
    -- permite preguntar "cómo ha evolucionado este dolor".
    cluster_key              text NOT NULL,
    label                    text NOT NULL,
    intent_type              text NOT NULL DEFAULT '',

    -- Vocabulario que sostiene la agrupación y foros donde apareció.
    keywords                 text[] NOT NULL DEFAULT '{}',
    subreddits               text[] NOT NULL DEFAULT '{}',

    mention_count            integer NOT NULL DEFAULT 0,
    community_count          integer NOT NULL DEFAULT 0,

    -- Señal que mejor explica el problema cuando hay que enseñar solo una.
    representative_signal_id uuid REFERENCES analyzed_signals(id) ON DELETE SET NULL,
    representative_reddit_id text,

    job_statement            text NOT NULL DEFAULT '',
    current_solutions        text[] NOT NULL DEFAULT '{}',
    risk_flags               text[] NOT NULL DEFAULT '{}',

    -- Desglose del scoring AGREGADO. Se guarda entero, no solo el total:
    -- un 73.5 no dice nada; "difusión 1.0, frecuencia 0.24" sí explica
    -- que el problema está extendido pero aún no es recurrente.
    spread_factor            numeric(5,4) NOT NULL DEFAULT 0,
    frequency_factor         numeric(5,4) NOT NULL DEFAULT 0,
    severity_factor          numeric(5,4) NOT NULL DEFAULT 0,
    recency_factor           numeric(5,4) NOT NULL DEFAULT 0,
    paid_signal_factor       numeric(5,4) NOT NULL DEFAULT 0,
    raw_score                numeric(6,3) NOT NULL DEFAULT 0,
    final_score              numeric(6,3) NOT NULL DEFAULT 0,
    urgency_tier             urgency_tier NOT NULL DEFAULT 'LOW',

    -- Si superó OPPORTUNITY_CLUSTER_THRESHOLD y no arrastra riesgos.
    qualified                boolean NOT NULL DEFAULT false,

    -- Citas literales para la ficha de detalle del frontend.
    evidence                 jsonb NOT NULL DEFAULT '[]'::jsonb,
    metadata                 jsonb NOT NULL DEFAULT '{}'::jsonb,

    created_at               timestamptz NOT NULL DEFAULT now(),
    updated_at               timestamptz NOT NULL DEFAULT now(),

    -- Una lectura por ejecución y problema.
    CONSTRAINT opportunity_clusters_run_key UNIQUE (tenant_id, run_id, cluster_key),
    CONSTRAINT opportunity_clusters_score_range CHECK (final_score BETWEEN 0 AND 100),
    CONSTRAINT opportunity_clusters_factors_range CHECK (
        spread_factor BETWEEN 0 AND 1 AND
        frequency_factor BETWEEN 0 AND 1 AND
        severity_factor BETWEEN 0 AND 1 AND
        recency_factor BETWEEN 0 AND 1 AND
        paid_signal_factor BETWEEN 0 AND 1
    ),
    CONSTRAINT opportunity_clusters_counts_positive CHECK (
        mention_count >= 0 AND community_count >= 0
    ),
    -- Un cluster no puede decir que abarca más comunidades que menciones.
    CONSTRAINT opportunity_clusters_community_le_mentions CHECK (
        community_count <= mention_count OR mention_count = 0
    )
);

CREATE TRIGGER opportunity_clusters_touch
    BEFORE UPDATE ON opportunity_clusters
    FOR EACH ROW EXECUTE FUNCTION radar.touch_updated_at();

-- El Radar View: oportunidades por puntuación.
CREATE INDEX opportunity_clusters_tenant_score_idx
    ON opportunity_clusters (tenant_id, final_score DESC, created_at DESC);

-- Lo que de verdad merece atención: cualificado y sin riesgos.
CREATE INDEX opportunity_clusters_qualified_idx
    ON opportunity_clusters (tenant_id, final_score DESC)
    WHERE qualified AND cardinality(risk_flags) = 0;

-- Evolución de un mismo problema a lo largo del tiempo.
CREATE INDEX opportunity_clusters_history_idx
    ON opportunity_clusters (tenant_id, cluster_key, created_at DESC);

CREATE INDEX opportunity_clusters_run_idx ON opportunity_clusters (run_id);
CREATE INDEX opportunity_clusters_tier_idx
    ON opportunity_clusters (tenant_id, urgency_tier, final_score DESC);

-- Búsqueda por término léxico, por foro y por riesgo.
CREATE INDEX opportunity_clusters_keywords_gin
    ON opportunity_clusters USING gin (keywords);
CREATE INDEX opportunity_clusters_subreddits_gin
    ON opportunity_clusters USING gin (subreddits);
CREATE INDEX opportunity_clusters_risks_gin
    ON opportunity_clusters USING gin (risk_flags);
CREATE INDEX opportunity_clusters_evidence_gin
    ON opportunity_clusters USING gin (evidence jsonb_path_ops);

-- 'simple' y no 'english': la etiqueta mezcla términos de dominio en
-- inglés con un job statement generado en español.
ALTER TABLE opportunity_clusters
    ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(label, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(job_statement, '')), 'B')
    ) STORED;

CREATE INDEX opportunity_clusters_search_gin
    ON opportunity_clusters USING gin (search_vector);


-- =====================================================================
-- OPPORTUNITY_CLUSTER_SIGNALS  (pivote N:M)
-- =====================================================================
-- Lleva `tenant_id` aunque sea derivable por join: permite aplicar RLS
-- directamente y filtrar sin cruzar tablas. Es la práctica habitual en
-- esquemas multi-inquilino, y el coste es una columna.

CREATE TABLE opportunity_cluster_signals (
    cluster_id        uuid NOT NULL REFERENCES opportunity_clusters(id) ON DELETE CASCADE,
    signal_id         uuid NOT NULL REFERENCES analyzed_signals(id) ON DELETE CASCADE,
    tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    is_representative boolean NOT NULL DEFAULT false,
    added_at          timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (cluster_id, signal_id)
);

-- La dirección contraria: "¿en qué oportunidades aparece esta queja?"
CREATE INDEX opportunity_cluster_signals_signal_idx
    ON opportunity_cluster_signals (signal_id);

CREATE INDEX opportunity_cluster_signals_tenant_idx
    ON opportunity_cluster_signals (tenant_id);

-- Solo una señal representa a cada cluster.
CREATE UNIQUE INDEX opportunity_cluster_signals_one_representative
    ON opportunity_cluster_signals (cluster_id)
    WHERE is_representative;


-- =====================================================================
-- VISTA
-- =====================================================================

CREATE VIEW v_opportunity_board AS
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
      WHERE cs.cluster_id = c.id) AS linked_signals
FROM opportunity_clusters c
LEFT JOIN pipeline_runs r ON r.id = c.run_id
LEFT JOIN analyzed_signals s ON s.id = c.representative_signal_id;

COMMENT ON VIEW v_opportunity_board IS
    'Tablero de oportunidades consolidadas para el Radar View del frontend.';


-- =====================================================================
-- ROW LEVEL SECURITY (definida, no activada — ver migración 001)
-- =====================================================================

CREATE POLICY tenant_isolation ON opportunity_clusters
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY tenant_isolation ON opportunity_cluster_signals
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);


COMMENT ON TABLE opportunity_clusters IS
    'Problemas recurrentes consolidados. Una fila por ejecución y cluster: el historial es la señal.';
COMMENT ON TABLE opportunity_cluster_signals IS
    'Qué señales sostienen cada oportunidad (N:M).';
COMMENT ON COLUMN opportunity_clusters.cluster_key IS
    'Clave natural estable del problema, para seguirlo entre ejecuciones.';

COMMIT;
