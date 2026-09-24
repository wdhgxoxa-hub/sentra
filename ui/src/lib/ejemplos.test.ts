/**
 * Ejemplos de búsqueda sacados de los nichos reales (AUD2-007).
 *
 * «Facturación rota» y «Migración lenta» eran de la demostración antigua y
 * el corpus real no habla de eso: un ejemplo que no encuentra nada
 * pertinente engaña. Ahora salen de las palabras clave de los veredictos
 * actuales; sin veredictos, no hay ejemplos.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { ejemplosDeBusqueda, MAX_EJEMPLOS } from "./ejemplos.ts";

const v = (...keywords: string[]) => ({ keywords });

test("dos palabras clave de cada nicho, sin repetir y como mucho cuatro", () => {
  const ejemplos = ejemplosDeBusqueda([
    v("code", "send", "sends"), v("error", "notification"), v("code", "send", "otra"),
    v("domain", "emails"), v("retry", "duplicate"), v("sexto", "nicho"),
  ]);
  assert.deepEqual(ejemplos, ["code send", "error notification", "domain emails", "retry duplicate"]);
  assert.equal(MAX_EJEMPLOS, 4);
});

test("sin veredictos o sin palabras clave no se inventa nada", () => {
  assert.deepEqual(ejemplosDeBusqueda([]), []);
  assert.deepEqual(ejemplosDeBusqueda([v()]), []);
});
