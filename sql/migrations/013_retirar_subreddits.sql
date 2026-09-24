-- ---------------------------------------------------------------------------
-- 013 · Fuera `subreddits` y los tipos del esquema antiguo
--        (AUD2-016; pedido por el usuario antes de E8)
-- ---------------------------------------------------------------------------
-- `subreddits` era de la pipeline de Reddit retirada en la 012 y solo seguía
-- viva porque `pipeline_runs.subreddit_id` la referenciaba; ningún código
-- escribe ese id (start_run ya no lo recibe). Se van la columna, su índice y
-- la tabla; las ejecuciones se quedan con su nombre (`subreddit_name`).
-- Con ellas se van los enums sin uso: los 8 que dejaron huérfanos las tablas
-- retiradas en la 012 y los 2 de `subreddits`. Sin CASCADE: si algo
-- inesperado dependiera de ellos, la migración falla en vez de arrastrarlo.
-- ---------------------------------------------------------------------------

SET search_path = radar, public;

DROP INDEX pipeline_runs_subreddit_started_idx;
ALTER TABLE pipeline_runs DROP CONSTRAINT pipeline_runs_subreddit_id_fkey;
ALTER TABLE pipeline_runs DROP COLUMN subreddit_id;

DROP TABLE subreddits;

DROP TYPE listing_sort;
DROP TYPE subreddit_status;
DROP TYPE buying_intent;
DROP TYPE pain_severity;
DROP TYPE sentiment_label;
DROP TYPE signal_source;
DROP TYPE urgency_level;
DROP TYPE urgency_tier;
DROP TYPE validation_status;
DROP TYPE willingness_to_pay;
