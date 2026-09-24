-- ---------------------------------------------------------------------------
-- 016 · Nombre del problema y caché de G0 (decisiones del usuario tras E8)
-- ---------------------------------------------------------------------------
-- El Radar usa el mismo nombre que el dossier: el que da G0 a un grupo que es
-- un mismo problema, en es y en en (`problem_name`, jsonb; nulo en mezclas y en
-- los veredictos anteriores). La comprobación de coherencia es estable: su
-- resultado se guarda por grupo (hash de sus pares id/frase) y versión del
-- revisor, y un grupo ya comprobado no se vuelve a preguntar.
-- ---------------------------------------------------------------------------

SET search_path = radar, public;

ALTER TABLE niche_verdicts ADD COLUMN problem_name jsonb;
ALTER TABLE niche_verdicts ADD CONSTRAINT niche_verdicts_problem_name
    CHECK (problem_name IS NULL OR jsonb_typeof(problem_name) = 'object');

CREATE TABLE coherence_checks (
    tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    group_hash  text NOT NULL,
    checker     text NOT NULL,
    result      jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, group_hash, checker),
    CONSTRAINT coherence_checks_hash CHECK (group_hash ~ '^[0-9a-f]{64}$')
);

-- Row level security (definida, no activada - ver migración 001).
CREATE POLICY tenant_isolation ON coherence_checks
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMENT ON TABLE coherence_checks IS
    'Caché de G0 (coherencia) por grupo y versión del revisor: el mismo grupo da el mismo resultado sin volver a preguntar.';
COMMENT ON COLUMN niche_verdicts.problem_name IS
    'Nombre del problema que da G0 ({"es", "en"}); el Radar y el dossier lo comparten.';
