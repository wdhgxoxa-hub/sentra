-- ---------------------------------------------------------------------------
-- 020 · Propósito «palabras_clave» en llm_usage (Fase 2, D1)
-- ---------------------------------------------------------------------------
-- Decisión de Walter (D1, opción A): Gemini propone las palabras clave del
-- escaneo y esa llamada cuenta para los topes. Se registra con su propio
-- propósito, no como «otros», para que se vea en qué se gasta. Solo amplía el
-- CHECK: no toca ninguna fila.
-- ---------------------------------------------------------------------------

SET search_path = radar, public;

ALTER TABLE llm_usage DROP CONSTRAINT llm_usage_purpose;
ALTER TABLE llm_usage ADD CONSTRAINT llm_usage_purpose CHECK (purpose IN
    ('etiquetado', 'g0', 'abogado', 'dossier', 'plan', 'prueba_clave', 'listado_modelos', 'otros',
     'palabras_clave'));
