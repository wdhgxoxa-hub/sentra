-- ---------------------------------------------------------------------------
-- 014 · Los veredictos pueden llevar G0 (coherencia del grupo)
--        (residuos de AUD2-001 y AUD2-006; decisión del usuario)
-- ---------------------------------------------------------------------------
-- G0 dice si los problemas del grupo son el mismo (una comprobación del LLM
-- por escaneo). Un veredicto nuevo lleva 9 compuertas; los ya guardados
-- siguen con 8 y valen tal cual. Cualquier otro número sigue siendo un error.
-- ---------------------------------------------------------------------------

SET search_path = radar, public;

ALTER TABLE niche_verdicts DROP CONSTRAINT niche_verdicts_gates;
ALTER TABLE niche_verdicts ADD CONSTRAINT niche_verdicts_gates
    CHECK (jsonb_typeof(gates) = 'array' AND jsonb_array_length(gates) IN (8, 9));
