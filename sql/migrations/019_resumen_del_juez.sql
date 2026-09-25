-- ---------------------------------------------------------------------------
-- 019 · Resumen del juez en la ejecución (Fase 1, B3)
-- ---------------------------------------------------------------------------
-- Decisión de Walter (opción A): el resumen del juez (piezas, las que pasan el
-- filtro, etiquetadas, dolor, grupos, veredictos...) se guarda con la
-- ejecución. Antes solo viajaba a la interfaz y se perdía. Las columnas de la
-- pipeline antigua que el flujo actual no escribe quedan documentadas; no se
-- borran ni se reutilizan con otro significado. `stored` son siempre las
-- piezas guardadas en la ejecución (el re-juicio ya no escribe ahí los
-- veredictos; las filas antiguas no se reescriben).
-- ---------------------------------------------------------------------------

SET search_path = radar, public;

ALTER TABLE pipeline_runs ADD COLUMN judge_summary jsonb;
ALTER TABLE pipeline_runs ADD CONSTRAINT pipeline_runs_judge_summary
    CHECK (judge_summary IS NULL OR jsonb_typeof(judge_summary) = 'object');

COMMENT ON COLUMN pipeline_runs.judge_summary IS
    'Resumen del juez de la ejecución (piezas, pasan el filtro, etiquetadas, dolor, grupos, veredictos, uso del LLM).';
COMMENT ON COLUMN pipeline_runs.stored IS
    'Piezas de evidencia guardadas por la ejecución (0 en un re-juicio: reutiliza las del origen).';
COMMENT ON COLUMN pipeline_runs.filtered_in IS 'pipeline antigua, sin uso: el filtro del juez va en judge_summary.kept.';
COMMENT ON COLUMN pipeline_runs.filtered_out IS 'pipeline antigua, sin uso: los descartes van en judge_summary.discarded.';
COMMENT ON COLUMN pipeline_runs.analyzed IS 'pipeline antigua, sin uso: lo etiquetado va en judge_summary.labeled.';
COMMENT ON COLUMN pipeline_runs.qualified IS 'pipeline antigua, sin uso.';
COMMENT ON COLUMN pipeline_runs.rejected IS 'pipeline antigua, sin uso.';
COMMENT ON COLUMN pipeline_runs.cycles IS 'pipeline antigua, sin uso.';
COMMENT ON COLUMN pipeline_runs.last_cursor IS 'pipeline antigua, sin uso.';
COMMENT ON COLUMN pipeline_runs.graph_version IS 'pipeline antigua, sin uso.';
