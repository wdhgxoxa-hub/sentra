/**
 * Resultado de un escaneo: qué significa y qué hacer ahora (Fase 2, P1).
 *
 * Cada final posible (con nichos para construir, solo para investigar, sin
 * nichos, sin nada traído, cortado por el tope de Gemini, cancelado) da un
 * caso y al menos un paso. Los textos son claves de i18n; las cifras salen del
 * resumen del juez y, si no lo hay (escaneos anteriores a la migración 019),
 * se dice que no hay detalle en vez de inventar.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { siguientePaso, type ResultadoDeEscaneo } from "./siguientePaso.ts";

const resumen = { items: 96, kept: 80, discarded: {}, competition: 0, labeled: 80, undetermined: {},
  clusters: 2, pain: 7, minAuthors: 5, verdicts: {}, llm: { model: "m", unavailable: null, calls: 3, stopReason: null } };

const escaneo = (cambios: Partial<ResultadoDeEscaneo["escaneo"]> = {}): ResultadoDeEscaneo["escaneo"] => ({
  runId: "r", name: "Facturas", startedAt: "2026-09-25T10:00:00-05:00",
  keywords: ["facturas impagadas", "cliente no paga", "reclamar pago", "unpaid invoices", "chasing payments",
    "late payment"],
  languages: ["es", "en"], fetched: 96, verdicts: 0, niches: 0, summary: resumen, stopReason: null, ...cambios,
});

const resultado = (cambios: Partial<ResultadoDeEscaneo> = {}): ResultadoDeEscaneo => ({
  escaneo: escaneo(), veredictos: [], cancelado: false, hayNichoAnterior: false, ...cambios,
});

const claves = (r: ResultadoDeEscaneo) => siguientePaso(r).pasos.map((p) => p.clave);

test("con algún CONSTRUIR: leer el dossier y generar el plan", () => {
  const r = resultado({ veredictos: [{ verdict: "CONSTRUIR" }, { verdict: "DESCARTAR" }] });
  assert.equal(siguientePaso(r).caso, "construir");
  assert.deepEqual(claves(r), ["leer_dossier", "generar_plan"]);
});

test("solo INVESTIGAR MÁS: leer el dossier y buscar lo que falta para confirmarlo", () => {
  const r = resultado({ veredictos: [{ verdict: "INVESTIGAR MÁS" }, { verdict: "DESCARTAR" }] });
  assert.equal(siguientePaso(r).caso, "investigar");
  assert.deepEqual(claves(r), ["leer_dossier", "ampliar_para_confirmar"]);
});

test("0 nichos con buena cobertura: describir el problema, no el producto", () => {
  const r = resultado({ veredictos: [{ verdict: "DESCARTAR" }] });
  const s = siguientePaso(r);
  assert.equal(s.caso, "cero_nichos");
  assert.deepEqual(claves(r), ["describir_problema"]);
  assert.deepEqual(s.cifras, { leidas: 96, conDolor: 7, personasNecesarias: 5 });
});

test("0 nichos con palabras en un solo idioma: primero añadir el otro idioma", () => {
  const r = resultado({ escaneo: escaneo({ keywords: ["facturas impagadas"], languages: ["es"] }) });
  assert.deepEqual(claves(r), ["anadir_otro_idioma", "mas_palabras", "describir_problema"]);
});

test("0 nichos con un nicho anterior: se dice que el Radar no cambia", () => {
  const r = resultado({ hayNichoAnterior: true });
  assert.deepEqual(claves(r), ["describir_problema", "radar_sigue"]);
});

test("las fuentes no trajeron nada: otras palabras o más antigüedad", () => {
  const r = resultado({ escaneo: escaneo({ fetched: 0, summary: null }) });
  assert.equal(siguientePaso(r).caso, "sin_piezas");
  assert.deepEqual(claves(r), ["otras_palabras", "mas_antiguedad"]);
});

test("cortado por un tope de Gemini: subir el tope o esperar a mañana", () => {
  const r = resultado({ escaneo: escaneo({ stopReason: "tope_escaneo_llamadas" }) });
  assert.equal(siguientePaso(r).caso, "tope_gemini");
  assert.deepEqual(claves(r), ["subir_tope_o_esperar"]);
});

test("cancelado: se guardó lo traído y se puede volver a escanear", () => {
  const r = resultado({ cancelado: true, veredictos: [{ verdict: "CONSTRUIR" }] });
  assert.equal(siguientePaso(r).caso, "cancelado");
  assert.deepEqual(claves(r), ["volver_a_escanear"]);
});

test("sin resumen del juez (anterior a la 019) no se inventan cifras", () => {
  const s = siguientePaso(resultado({ escaneo: escaneo({ summary: null }) }));
  assert.equal(s.caso, "cero_nichos");
  assert.equal(s.cifras, null);
  assert.equal(s.sinDetalle, true);
});

test("ningún caso se queda sin paso", () => {
  const casos = [
    resultado(), resultado({ cancelado: true }), resultado({ escaneo: escaneo({ fetched: 0 }) }),
    resultado({ escaneo: escaneo({ stopReason: "tope_diario_tokens" }) }),
    resultado({ veredictos: [{ verdict: "CONSTRUIR" }] }), resultado({ veredictos: [{ verdict: "INVESTIGAR MÁS" }] }),
  ];
  for (const r of casos) assert.ok(siguientePaso(r).pasos.length >= 1, siguientePaso(r).caso);
});
