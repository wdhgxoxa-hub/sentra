/**
 * Resultado de un escaneo (Fase 2): la marca de «Nuevo escaneo» (D3), el
 * reparto de los veredictos en nichos y descartados, y el tono de cada caso.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { marcaTrasEvento, repartirVeredictos, tonoDelCaso } from "./resultado.ts";

test("D3: al terminar fuera de «Nuevo escaneo», se marca; dentro, no", () => {
  const juezListo = { type: "judge:done" } as const;
  assert.equal(marcaTrasEvento(juezListo, "radar"), true);
  assert.equal(marcaTrasEvento(juezListo, "nuevo"), false);
  assert.equal(marcaTrasEvento({ type: "judge:error" }, "sources"), true);
  assert.equal(marcaTrasEvento({ type: "error" }, "settings"), true);
});

test("D3: un escaneo guardado espera al juez; uno sin guardar termina ya", () => {
  assert.equal(marcaTrasEvento({ type: "scan:done", persisted: true }, "radar"), false);
  assert.equal(marcaTrasEvento({ type: "scan:done", persisted: false }, "radar"), true);
  assert.equal(marcaTrasEvento({ type: "source:done" }, "radar"), false);
});

test("los veredictos se reparten en nichos (CONSTRUIR, INVESTIGAR MÁS) y descartados, en su orden", () => {
  const v = (id: string, verdict: "CONSTRUIR" | "INVESTIGAR MÁS" | "DESCARTAR") => ({ id, verdict });
  const { nichos, descartados } = repartirVeredictos(
    [v("a", "CONSTRUIR"), v("b", "DESCARTAR"), v("c", "INVESTIGAR MÁS")],
    [v("d", "DESCARTAR")],
  );
  assert.deepEqual(nichos.map((x) => x.id), ["a", "c"]);
  assert.deepEqual(descartados.map((x) => x.id), ["b", "d"]);
});

test("cada caso tiene su tono, y no solo color: también su palabra en el título", () => {
  assert.equal(tonoDelCaso("construir"), "bien");
  assert.equal(tonoDelCaso("investigar"), "info");
  assert.equal(tonoDelCaso("cero_nichos"), "aviso");
  assert.equal(tonoDelCaso("sin_piezas"), "aviso");
  assert.equal(tonoDelCaso("tope_gemini"), "mal");
  assert.equal(tonoDelCaso("cancelado"), "info");
});
