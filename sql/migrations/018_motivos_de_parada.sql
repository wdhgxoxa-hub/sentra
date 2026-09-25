-- ---------------------------------------------------------------------------
-- 018 · Motivos de parada (Fase 1, B4)
-- ---------------------------------------------------------------------------
-- Cuando una ejecución o una fuente se corta, el motivo queda guardado.
-- `pipeline_runs.stop_reason`: por qué se paró la ejecución (hoy, un tope de
-- Gemini: tope_escaneo_llamadas, tope_diario_tokens...; el detalle está en la
-- fila «cortada» de llm_usage). NULL = terminó sin cortes.
-- `run_source_outcomes`: cómo terminó cada fuente en cada ejecución (estado,
-- motivo de parada, error, detalle y lo que gastó). Antes el «500 de 500
-- ítems» de YouTube solo viajaba a la interfaz y se perdía.
-- ---------------------------------------------------------------------------

SET search_path = radar, public;

ALTER TABLE pipeline_runs ADD COLUMN stop_reason text;

CREATE TABLE run_source_outcomes (
    tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    run_id       uuid NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    source       text NOT NULL,
    status       text NOT NULL,
    stop_reason  text,
    error_code   text,
    detail       text,
    items        integer NOT NULL DEFAULT 0,
    requests     integer NOT NULL DEFAULT 0,
    units        numeric NOT NULL DEFAULT 0,
    usd          numeric NOT NULL DEFAULT 0,
    created_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, source),
    CONSTRAINT run_source_outcomes_status CHECK (status IN ('running', 'done', 'failed')),
    CONSTRAINT run_source_outcomes_no_negativos CHECK (
        items >= 0 AND requests >= 0 AND units >= 0 AND usd >= 0)
);

-- Row level security (definida, no activada - ver migración 001).
CREATE POLICY tenant_isolation ON run_source_outcomes
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMENT ON COLUMN pipeline_runs.stop_reason IS
    'Por qué se paró la ejecución (tope de Gemini); NULL si terminó sin cortes.';
COMMENT ON TABLE run_source_outcomes IS
    'Cómo terminó cada fuente en cada ejecución: estado, motivo de parada, error y gasto.';
