-- ---------------------------------------------------------------------------
-- 012 · Fuera la demostración antigua y el esquema de la pipeline de Reddit
--        (AUD2-002, AUD2-016; decisiones DP3 A y DP4 A)
-- ---------------------------------------------------------------------------
-- 1. La evidencia sin procedencia (fuente `legacy`, data_source NULL) son
--    fixtures de la demostración antigua del 21/09, fechadas el 31/12/2099
--    y con URLs inventadas. La interfaz las enseñaba arriba de «Evidencia
--    reciente» y en la búsqueda. Se borran, y la procedencia pasa a ser
--    obligatoria para que nada vuelva a entrar sin ella; sin la excepción
--    `legacy`, toda evidencia lleva su enlace al original (R5).
-- 2. Las tablas, vistas y columnas de la pipeline antigua no las usa ningún
--    código (tests/test_esquema_legado.py lo vigila). Sin CASCADE: si algo
--    inesperado dependiera de ellas, la migración falla en lugar de
--    arrastrarlo en silencio.
-- La tabla `subreddits` se queda: `pipeline_runs.subreddit_id` la referencia
-- y retirarla exige tocar una tabla viva (queda anotado en la auditoría).
-- ---------------------------------------------------------------------------

SET search_path = radar, public;

-- 0. Vistas antiguas primero: v_radar_feed lee evidence_items.legacy_post_id.

DROP VIEW v_opportunity_board;
DROP VIEW v_radar_feed;
DROP VIEW v_subreddit_health;

-- 1. Evidencia sin procedencia -----------------------------------------------

DELETE FROM evidence_items WHERE source = 'legacy' AND data_source IS NULL;

ALTER TABLE evidence_items ALTER COLUMN data_source SET NOT NULL;

ALTER TABLE evidence_items DROP CONSTRAINT evidence_items_url;
-- IS NOT NULL explícito: un CHECK con NULL no falla, y dejaría pasar filas sin enlace.
ALTER TABLE evidence_items ADD CONSTRAINT evidence_items_url CHECK (url IS NOT NULL AND url LIKE 'https://%');

DROP INDEX evidence_items_legacy_post_idx;
ALTER TABLE evidence_items DROP COLUMN legacy_post_id;
ALTER TABLE evidence_items DROP COLUMN legacy_comment_id;

-- 2. Esquema de la pipeline antigua --------------------------------------------

DROP TABLE cluster_validations;
DROP TABLE opportunity_cluster_signals;
DROP TABLE opportunity_clusters;
DROP TABLE jtbd_opportunities;
DROP TABLE analyzed_signals;
DROP TABLE raw_comments;
DROP TABLE raw_posts;
