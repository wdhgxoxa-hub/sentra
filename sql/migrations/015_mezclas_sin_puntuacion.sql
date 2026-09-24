-- ---------------------------------------------------------------------------
-- 015 · Un grupo sin problema común no lleva puntuación (decisión del usuario)
-- ---------------------------------------------------------------------------
-- G0 descarta como mezcla los grupos cuyos problemas no son el mismo. Su
-- puntuación salía de las dimensiones de la mezcla y confundía (61,7/100 en
-- un grupo descartado). `score` admite NULL (la cota 0–100 se mantiene) y los
-- veredictos ya guardados con la regla 0 la pierden; el resto la conserva.
-- ---------------------------------------------------------------------------

SET search_path = radar, public;

ALTER TABLE niche_verdicts ALTER COLUMN score DROP NOT NULL;

UPDATE niche_verdicts SET score = NULL WHERE rule LIKE '0:%';
