-- =====================================================================
-- 004 - Etiqueta "undetermined" en las clasificaciones (AUD-005)
-- =====================================================================
--
-- Sin evidencia suficiente, el clasificador responde "undetermined" en
-- lugar de la primera etiqueta de su lista, que era la mas extrema
-- ("ready to buy", "severe blocker", "negative frustration"). Una senal
-- indeterminada aporta cero a su componente de la puntuacion.
--
-- ADD VALUE admite ir dentro de una transaccion (PostgreSQL >= 12) siempre
-- que el valor nuevo no se use en ella, y aqui no se usa.

BEGIN;

SET search_path = radar, public;

ALTER TYPE buying_intent   ADD VALUE IF NOT EXISTS 'undetermined';
ALTER TYPE pain_severity   ADD VALUE IF NOT EXISTS 'undetermined';
ALTER TYPE sentiment_label ADD VALUE IF NOT EXISTS 'undetermined';

COMMIT;
