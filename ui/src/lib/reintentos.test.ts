/**
 * Política de reintentos de las consultas (node --test, sin dependencias).
 *
 * El motor tarda unos segundos en arrancar (hasta 30 s: 60 sondeos de
 * 500 ms). Una vista que consulta antes recibe `sidecar_unreachable`; con un
 * solo reintento a 1 s se quedaba vacía para siempre. Ese código se reintenta
 * con espera creciente durante la ventana de arranque; cualquier otro error
 * se reintenta como antes (o nada), para no esconder fallos reales.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { esperaDeReintento, reintentarMientrasArranca, VENTANA_DE_ARRANQUE_MS } from "./reintentos.ts";

const motorAusente = { code: "sidecar_unreachable", detail: "connection refused" };

test("mientras el motor arranca se reintenta durante toda la ventana de arranque", () => {
  const politica = reintentarMientrasArranca(1);
  let esperado = 0;
  let fallos = 0;
  while (politica(fallos, motorAusente)) {
    esperado += esperaDeReintento(fallos);
    fallos += 1;
  }
  assert.ok(esperado >= VENTANA_DE_ARRANQUE_MS, `solo espera ${esperado} ms`);
  assert.ok(esperado <= VENTANA_DE_ARRANQUE_MS + 10_000, `espera de más: ${esperado} ms`);
});

test("otros errores conservan su número de reintentos", () => {
  const conUno = reintentarMientrasArranca(1);
  assert.equal(conUno(0, { code: "database", detail: "" }), true);
  assert.equal(conUno(1, { code: "database", detail: "" }), false);
  const sinReintento = reintentarMientrasArranca(0);
  assert.equal(sinReintento(0, { code: "gemini_key_rejected", detail: "" }), false);
  assert.equal(sinReintento(0, new Error("x")), false);
});

test("un motor lento que ya contesta no se reintenta como si arrancara", () => {
  assert.equal(reintentarMientrasArranca(0)(0, { code: "sidecar_timeout", detail: "" }), false);
});

test("la espera crece y tiene techo", () => {
  assert.equal(esperaDeReintento(0), 500);
  assert.equal(esperaDeReintento(1), 1_000);
  assert.ok(esperaDeReintento(20) <= 5_000);
});
