/**
 * Aviso del Radar (Fase 2): un escaneo vacío no borra el último nicho válido,
 * pero el Radar dice que el último escaneo no formó ninguno y cuándo fue, para
 * no presentar los nichos anteriores como si fueran de ahora (AUD2-001).
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { avisoDelUltimoEscaneo } from "./radar.ts";

const escaneo = (runId: string, name: string, startedAt: string) => ({
  runId, name, startedAt, keywords: [], languages: [], fetched: 0, verdicts: 0, niches: 0,
  summary: null, stopReason: null, sources: {},
});

const conNicho = escaneo("a", "Facturas", "2026-09-24T17:56:00-05:00");
const vacio = escaneo("b", "Pagos", "2026-09-24T18:47:00-05:00");

test("si el último escaneo no es el que se enseña, se avisa con su nombre y su fecha", () => {
  assert.deepEqual(avisoDelUltimoEscaneo({ run: conNicho, latestRun: vacio }), {
    nombre: "Pagos", fecha: "2026-09-24T18:47:00-05:00", runId: "b",
  });
});

test("si el que se enseña es el último, no hay aviso", () => {
  assert.equal(avisoDelUltimoEscaneo({ run: conNicho, latestRun: conNicho }), null);
});

test("sin ningún escaneo juzgado, no hay aviso", () => {
  assert.equal(avisoDelUltimoEscaneo({ run: null, latestRun: null }), null);
});
