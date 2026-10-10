-- ---------------------------------------------------------------------------
-- 021 · Propuestas de escaneo (servidor MCP)
-- ---------------------------------------------------------------------------
-- Decisión de Walter (2026-10-09): Claude Desktop lee SENTRA por MCP, pero no
-- gasta. Para escanear deja aquí una propuesta (el perfil y su motivo); SENTRA
-- la enseña con la estimación de siempre y el escaneo solo arranca si Walter
-- pulsa «Lanzar» en la ventana. El motor sigue sin aceptar a nadie más (D-B).
-- `status`: pendiente → lanzada (con su ejecución, si se guardó) o descartada.
-- Toda propuesta resuelta lleva `resolved_at`.
-- ---------------------------------------------------------------------------

SET search_path = radar, public;

CREATE TABLE scan_requests (
    id           uuid PRIMARY KEY DEFAULT uuidv7(),
    tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    profile      jsonb NOT NULL,
    reason       text NOT NULL DEFAULT '',
    origin       text NOT NULL DEFAULT 'mcp',
    status       text NOT NULL DEFAULT 'pendiente',
    run_id       uuid REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    resolved_at  timestamptz,
    CONSTRAINT scan_requests_status CHECK (status IN ('pendiente', 'lanzada', 'descartada')),
    CONSTRAINT scan_requests_resuelta CHECK ((status = 'pendiente') = (resolved_at IS NULL)),
    CONSTRAINT scan_requests_run CHECK (run_id IS NULL OR status = 'lanzada'),
    CONSTRAINT scan_requests_profile CHECK (jsonb_typeof(profile) = 'object'),
    CONSTRAINT scan_requests_reason CHECK (char_length(reason) <= 500)
);

CREATE INDEX scan_requests_pendientes ON scan_requests (tenant_id, created_at) WHERE status = 'pendiente';

-- Row level security (definida, no activada - ver migración 001).
CREATE POLICY tenant_isolation ON scan_requests
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMENT ON TABLE scan_requests IS
    'Escaneos propuestos desde Claude Desktop (MCP): solo se lanzan desde la ventana de SENTRA.';
