/** Rellenar plantillas de i18n: cada {clave} con su valor, todas las veces. */
import assert from "node:assert/strict";
import { test } from "node:test";

import { rellenar } from "./texto.ts";

test("cambia cada marcador, aunque se repita, y deja los que no conoce", () => {
  assert.equal(rellenar("{n} de {total} · {n}", { n: 3, total: 8 }), "3 de 8 · 3");
  assert.equal(rellenar("Hola {nombre}", {}), "Hola {nombre}");
});
