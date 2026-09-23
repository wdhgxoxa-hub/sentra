-- =====================================================================
-- 010 - Juez de nichos (F3, decisión D-M1)
-- =====================================================================
--
-- evidence_labels: caché de etiquetas del LLM por hash de contenido y
--   etiquetador (versión + modelo): el mismo texto no se etiqueta dos veces.
-- niche_verdicts: un veredicto por grupo juzgado, con la regla D-M3 que
--   decidió, las ocho compuertas (valor, umbral, ids), las siete
--   dimensiones, la versión de pesos y el abogado del diablo.
-- cluster_evidence: los miembros de cada grupo juzgado.
--
-- Solo tablas nuevas: ningún dato existente cambia.

BEGIN;

SET search_path = radar, public;

CREATE TABLE evidence_labels (
    tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    content_hash  text NOT NULL,
    labeler       text NOT NULL,
    label         jsonb NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, content_hash, labeler),
    CONSTRAINT evidence_labels_hash CHECK (content_hash ~ '^[0-9a-f]{64}$')
);

CREATE TABLE niche_verdicts (
    id               uuid PRIMARY KEY DEFAULT uuidv7(),
    tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    run_id           uuid NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    opportunity_id   uuid,
    cluster_key      text NOT NULL,
    keywords         text[] NOT NULL DEFAULT '{}',
    verdict          text NOT NULL,
    rule             text NOT NULL,
    score            numeric(6, 2) NOT NULL,
    weights_version  text NOT NULL,
    missing          text[] NOT NULL DEFAULT '{}',
    gates            jsonb NOT NULL,
    dimensions       jsonb NOT NULL,
    advocate         jsonb NOT NULL DEFAULT '{}'::jsonb,
    member_count     integer NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT niche_verdicts_verdict CHECK (verdict IN ('CONSTRUIR', 'INVESTIGAR MÁS', 'DESCARTAR')),
    CONSTRAINT niche_verdicts_score CHECK (score >= 0 AND score <= 100),
    CONSTRAINT niche_verdicts_members CHECK (member_count > 0),
    CONSTRAINT niche_verdicts_gates CHECK (jsonb_typeof(gates) = 'array' AND jsonb_array_length(gates) = 8),
    UNIQUE (run_id, cluster_key)
);

CREATE INDEX niche_verdicts_run_idx ON niche_verdicts (tenant_id, run_id);
CREATE INDEX niche_verdicts_opportunity_idx ON niche_verdicts (tenant_id, opportunity_id, created_at DESC);

CREATE TABLE cluster_evidence (
    tenant_id    uuid NOT NULL,
    verdict_id   uuid NOT NULL REFERENCES niche_verdicts(id) ON DELETE CASCADE,
    evidence_id  text NOT NULL,
    PRIMARY KEY (verdict_id, evidence_id),
    FOREIGN KEY (tenant_id, evidence_id) REFERENCES evidence_items (tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX cluster_evidence_evidence_idx ON cluster_evidence (tenant_id, evidence_id);

-- Row level security (definida, no activada - ver migración 001).
CREATE POLICY tenant_isolation ON evidence_labels
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY tenant_isolation ON niche_verdicts
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY tenant_isolation ON cluster_evidence
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMENT ON TABLE evidence_labels IS
    'Caché de etiquetas verificadas del LLM por hash de contenido y etiquetador (F3.2).';
COMMENT ON TABLE niche_verdicts IS
    'Veredicto determinista del juez por grupo: compuertas G1-G8, dimensiones y abogado del diablo.';
COMMENT ON TABLE cluster_evidence IS
    'Miembros de cada grupo juzgado (evidencia que sostiene el veredicto).';

COMMIT;
