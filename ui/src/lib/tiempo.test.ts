/**
 * Cuánto hace que se pidió algo a Google (AUD2-019).
 *
 * La lista de modelos de Gemini se guarda un día; la configuración dice
 * cuándo se pidió de verdad, en lugar de callar la llamada.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { haceCuanto } from "./tiempo.ts";

const AHORA = new Date("2026-09-24T12:00:00Z");

test("minutos, horas y días en el idioma de la interfaz", () => {
  assert.equal(haceCuanto("2026-09-24T11:55:00+00:00", AHORA, "es"), "hace 5 minutos");
  assert.equal(haceCuanto("2026-09-24T09:00:00+00:00", AHORA, "es"), "hace 3 horas");
  assert.equal(haceCuanto("2026-09-23T12:00:00+00:00", AHORA, "en"), "yesterday");
});

test("menos de un minuto es ahora", () => {
  assert.equal(haceCuanto("2026-09-24T11:59:40+00:00", AHORA, "es"), "ahora");
});

test("sin fecha, o ilegible, no inventa nada", () => {
  assert.equal(haceCuanto(null, AHORA, "es"), null);
  assert.equal(haceCuanto("ayer por la tarde", AHORA, "es"), null);
});
