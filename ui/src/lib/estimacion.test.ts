/**
 * Pantalla de confirmación antes de escanear (Fase 1, B4).
 *
 * El motor da un rango estimado de llamadas y tokens, lo gastado hoy y lo que
 * queda. La pantalla lo enseña como rango («estimado») y solo deja confirmar
 * si hoy queda presupuesto.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { cifrasDeLaEstimacion, sePuedeConfirmar } from "./estimacion.ts";

const ESTIMACION = {
  estimated: true,
  calls: { min: 0, max: 19 },
  tokens: { min: 0, max: 475000 },
  spentToday: { calls: 3, tokens: 45000 },
  leftToday: { calls: 37, tokens: 955000 },
  withHistory: false,
  canScan: true,
};

test("rangos y cifras con separador de miles del idioma", () => {
  assert.deepEqual(cifrasDeLaEstimacion(ESTIMACION, "es"), {
    llamadas: "0–19",
    tokens: "0–475.000",
    gastadoLlamadas: "3",
    gastadoTokens: "45.000",
    quedaLlamadas: "37",
    quedaTokens: "955.000",
  });
  assert.equal(cifrasDeLaEstimacion(ESTIMACION, "en").tokens, "0–475,000");
});

test("un rango sin anchura se da como un solo número", () => {
  const cero = { ...ESTIMACION, calls: { min: 0, max: 0 }, tokens: { min: 0, max: 0 } };
  assert.equal(cifrasDeLaEstimacion(cero, "es").llamadas, "0");
});

test("sin presupuesto hoy no se puede confirmar", () => {
  assert.equal(sePuedeConfirmar(ESTIMACION), true);
  assert.equal(sePuedeConfirmar({ ...ESTIMACION, canScan: false }), false);
  assert.equal(sePuedeConfirmar({ ...ESTIMACION, calls: { min: 0, max: 0 } }), false);
});
