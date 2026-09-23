-- =====================================================================
-- 008 - Identidad estable de cada oportunidad (AUD-019, decision D-G)
-- =====================================================================
--
-- `cluster_key` (intencion + palabras clave) describe una lectura y cambia
-- en cuanto el problema gana o pierde una palabra entre escaneos: con ella
-- como enlace, el historial se partia y la validacion humana se perdia.
-- Cada oportunidad tiene ahora un UUID (`opportunity_id`) que la lectura
-- nueva hereda de una anterior segun core/orchestration/identity.py.
--
-- Relleno: cada clave existente recibe su propio UUID, de modo que el
-- historial que ya estaba unido por clave sigue unido. Las validaciones lo
-- heredan de su clave; una validacion sin ninguna lectura recibe uno nuevo.
--
-- `cluster_key` se conserva: en las lecturas es su descripcion, y en las
-- validaciones, la ultima clave vista (informativa, ya no es la clave).

BEGIN;

SET search_path = radar, public;

-- --- Lecturas ---------------------------------------------------------

ALTER TABLE opportunity_clusters ADD COLUMN opportunity_id uuid;

WITH claves AS (
    SELECT tenant_id, cluster_key, uuidv7() AS opportunity_id
    FROM (SELECT DISTINCT tenant_id, cluster_key FROM opportunity_clusters) d
)
UPDATE opportunity_clusters c
   SET opportunity_id = k.opportunity_id
  FROM claves k
 WHERE c.tenant_id = k.tenant_id AND c.cluster_key = k.cluster_key;

-- Sin valor por defecto a proposito: una lectura sin identidad asignada es
-- un fallo del motor y tiene que notarse, no convertirse en otra oportunidad.
ALTER TABLE opportunity_clusters ALTER COLUMN opportunity_id SET NOT NULL;

CREATE INDEX opportunity_clusters_opportunity_idx
    ON opportunity_clusters (tenant_id, opportunity_id, created_at DESC);

COMMENT ON COLUMN opportunity_clusters.opportunity_id IS
    'Identidad estable de la oportunidad entre escaneos (D-G).';

-- --- Validaciones -----------------------------------------------------

ALTER TABLE cluster_validations ADD COLUMN opportunity_id uuid;

UPDATE cluster_validations v
   SET opportunity_id = c.opportunity_id
  FROM (SELECT DISTINCT tenant_id, cluster_key, opportunity_id
          FROM opportunity_clusters) c
 WHERE v.tenant_id = c.tenant_id AND v.cluster_key = c.cluster_key;

UPDATE cluster_validations SET opportunity_id = uuidv7() WHERE opportunity_id IS NULL;

ALTER TABLE cluster_validations ALTER COLUMN opportunity_id SET NOT NULL;
ALTER TABLE cluster_validations DROP CONSTRAINT cluster_validations_pkey;
ALTER TABLE cluster_validations ADD PRIMARY KEY (tenant_id, opportunity_id);

COMMENT ON COLUMN cluster_validations.opportunity_id IS
    'Oportunidad juzgada (D-G): el juicio sobrevive a los cambios de palabras clave.';
COMMENT ON COLUMN cluster_validations.cluster_key IS
    'Ultima clave vista de la oportunidad al juzgarla (informativa).';

-- --- Tablero ----------------------------------------------------------
-- Igual que en 006, con la validacion unida por identidad y la identidad
-- expuesta al final.

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
    r.data_source,
    c.opportunity_id
FROM opportunity_clusters c
LEFT JOIN pipeline_runs r ON r.id = c.run_id
LEFT JOIN analyzed_signals s ON s.id = c.representative_signal_id
LEFT JOIN cluster_validations v
       ON v.tenant_id = c.tenant_id AND v.opportunity_id = c.opportunity_id;

COMMIT;
