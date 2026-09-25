-- ---------------------------------------------------------------------------
-- 017 · Uso y topes de Gemini (Fase 1, B4)
-- ---------------------------------------------------------------------------
-- El presupuesto de Gemini deja de ser un contador a mano. Cada intento de
-- llamada, reintentos incluidos, deja una fila en `llm_usage`: los que salen
-- (`ok` o `error`) y los que el tope no deja salir (`cortada`, sin tokens).
-- Los topes viven en `llm_budget_settings`, uno por instalación, con los
-- valores aprobados por el usuario: 20 llamadas y 500 000 tokens por escaneo,
-- 40 llamadas y 1 000 000 tokens por día (día en hora de Lima). Un tope a 0
-- no deja salir ninguna llamada de ese tipo.
-- ---------------------------------------------------------------------------

SET search_path = radar, public;

CREATE TABLE llm_usage (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    run_id          uuid REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    model           text NOT NULL,
    purpose         text NOT NULL,
    outcome         text NOT NULL,
    error_code      text,
    -- NULL = el proveedor no lo informó (no es 0).
    input_tokens    integer,
    output_tokens   integer,
    thinking_tokens integer,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT llm_usage_purpose CHECK (purpose IN
        ('etiquetado', 'g0', 'abogado', 'dossier', 'plan', 'prueba_clave', 'listado_modelos', 'otros')),
    CONSTRAINT llm_usage_outcome CHECK (outcome IN ('ok', 'error', 'cortada')),
    CONSTRAINT llm_usage_tokens CHECK (
        coalesce(input_tokens, 0) >= 0 AND coalesce(output_tokens, 0) >= 0
        AND coalesce(thinking_tokens, 0) >= 0)
);

CREATE INDEX llm_usage_tenant_created ON llm_usage (tenant_id, created_at);
CREATE INDEX llm_usage_run ON llm_usage (run_id) WHERE run_id IS NOT NULL;

CREATE TABLE llm_budget_settings (
    tenant_id         uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    scan_max_calls    integer NOT NULL DEFAULT 20,
    scan_max_tokens   integer NOT NULL DEFAULT 500000,
    daily_max_calls   integer NOT NULL DEFAULT 40,
    daily_max_tokens  integer NOT NULL DEFAULT 1000000,
    updated_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT llm_budget_settings_no_negativos CHECK (
        scan_max_calls >= 0 AND scan_max_tokens >= 0
        AND daily_max_calls >= 0 AND daily_max_tokens >= 0)
);

INSERT INTO llm_budget_settings (tenant_id) SELECT id FROM tenants;

-- Row level security (definida, no activada - ver migración 001).
CREATE POLICY tenant_isolation ON llm_usage
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY tenant_isolation ON llm_budget_settings
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMENT ON TABLE llm_usage IS
    'Cada intento de llamada a Gemini: ok o error (salió) o cortada (el tope no la dejó salir).';
COMMENT ON TABLE llm_budget_settings IS
    'Topes de Gemini por escaneo y por día (hora de Lima); se editan en Configuración.';
