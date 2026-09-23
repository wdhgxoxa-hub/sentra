-- =====================================================================
-- 005 - Resultado Top N de cada ejecucion y fuente de los datos (AUD-007)
-- =====================================================================
--
-- Cada ejecucion termina con un resultado explicito: completo (N/N) o
-- incompleto (k/N) con un motivo tipado. Se guarda en la propia ejecucion,
-- junto con la fuente de los datos (demostracion o Reddit), y cada problema
-- del ranking guarda su posicion (1..N) para que la interfaz lo lea tal
-- cual, sin recalcular ni repetir el criterio.
--
-- N no se fija aqui: lo escribe el motor (core/orchestration/top_n.py) en
-- top_n_target, que es su unico origen.

BEGIN;

SET search_path = radar, public;

CREATE TYPE top_n_reason AS ENUM (
    'fuentes_agotadas',     -- la fuente se agoto con N problemas o mas, pero no cualifican N
    'limite_ciclos',        -- se alcanzo el tope de vueltas con fuente por delante
    'sin_acceso_reddit',    -- la fuente no entrego datos (AUD-003)
    'datos_insuficientes'   -- la fuente se agoto sin llegar a N problemas
);

ALTER TABLE pipeline_runs
    ADD COLUMN top_n_target smallint CHECK (top_n_target > 0),
    ADD COLUMN top_n_found  smallint CHECK (top_n_found >= 0),
    ADD COLUMN top_n_reason top_n_reason,
    ADD COLUMN data_source  text CHECK (data_source IN ('demo', 'reddit')),
    ADD CONSTRAINT pipeline_runs_top_n_coherente CHECK (
        top_n_target IS NULL
        OR (top_n_found <= top_n_target
            AND (top_n_reason IS NULL) = (top_n_found = top_n_target))
    );

ALTER TABLE opportunity_clusters
    ADD COLUMN top_rank smallint CHECK (top_rank >= 1);

CREATE INDEX opportunity_clusters_top_rank_idx
    ON opportunity_clusters (run_id, top_rank)
    WHERE top_rank IS NOT NULL;

COMMENT ON COLUMN pipeline_runs.top_n_target IS
    'Cuantas oportunidades busca la ejecucion (TOP_N del motor).';
COMMENT ON COLUMN pipeline_runs.top_n_found IS
    'Cuantas oportunidades cualificadas entrego (nunca rellenadas).';
COMMENT ON COLUMN pipeline_runs.top_n_reason IS
    'Por que no llego a top_n_target; NULL si llego.';
COMMENT ON COLUMN pipeline_runs.data_source IS
    'Fuente de los datos: demo (corpus fabricado) o reddit.';
COMMENT ON COLUMN opportunity_clusters.top_rank IS
    'Posicion en el Top N de su ejecucion (1 = mejor); NULL si no entra.';

COMMIT;
