-- =====================================================================
-- 011 - Veredictos versionados (B4)
-- =====================================================================
--
-- Cada veredicto guarda con qué versiones se produjo: etiquetador
-- (versión + modelo), agrupación y pesos (ya estaba). Así la interfaz
-- marca como antiguos los veredictos de versiones anteriores.
--
-- Filas existentes: clustering-v1 es cierto para todas (era el único
-- método). El etiquetador no se guardó: queda NULL = desconocido; no se
-- infiere.

BEGIN;

SET search_path = radar, public;

ALTER TABLE niche_verdicts
    ADD COLUMN labeler_version    text,
    ADD COLUMN clustering_version text;

UPDATE niche_verdicts SET clustering_version = 'clustering-v1' WHERE clustering_version IS NULL;

ALTER TABLE niche_verdicts ALTER COLUMN clustering_version SET NOT NULL;

COMMENT ON COLUMN niche_verdicts.labeler_version IS
    'Etiquetador (versión/modelo) que produjo las etiquetas; NULL = desconocido (anterior a la 011).';
COMMENT ON COLUMN niche_verdicts.clustering_version IS
    'Versión de la agrupación (clustering-v1: líder 0,86; clustering-v2: enlace promedio 0,82).';

COMMIT;
