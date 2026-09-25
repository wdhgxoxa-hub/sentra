/**
 * Estado de una fuente en una frase (Fase 2, P1): la fila de Fuentes dice si
 * está lista, sin probar, fallando, sin conectar, apagada o fuera por el modo
 * comercial, con su tono. Nada solo por color: cada estado es una clave de
 * texto.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { estadoDeLaFila } from "./fuentes.ts";

const tarjeta = (cambios: Record<string, unknown>) =>
  ({ status: "verificada", active: true, disabled: false, excludedByCommercialMode: false, ...cambios }) as Parameters<
    typeof estadoDeLaFila
  >[0];

test("lista si está verificada y entra en el escaneo", () => {
  assert.deepEqual(estadoDeLaFila(tarjeta({})), { clave: "lista", tono: "bien" });
});

test("apagada por la persona, antes que cualquier otra cosa", () => {
  assert.deepEqual(estadoDeLaFila(tarjeta({ status: "deshabilitada_por_usuario", disabled: true, active: false })), {
    clave: "apagada", tono: "neutro",
  });
});

test("fuera por el modo comercial", () => {
  assert.deepEqual(estadoDeLaFila(tarjeta({ excludedByCommercialMode: true, active: false })), {
    clave: "fuera_comercial", tono: "neutro",
  });
});

test("fallo, sin probar y sin conectar", () => {
  assert.equal(estadoDeLaFila(tarjeta({ status: "error", active: false })).clave, "fallo");
  assert.equal(estadoDeLaFila(tarjeta({ status: "error", active: false })).tono, "mal");
  assert.equal(estadoDeLaFila(tarjeta({ status: "configurada_sin_verificar" })).clave, "sin_probar");
  assert.equal(estadoDeLaFila(tarjeta({ status: "no_configurada", active: false })).clave, "sin_conectar");
});
