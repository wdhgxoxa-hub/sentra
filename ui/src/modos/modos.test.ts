/**
 * Modos (Fase 2, principio P2 de Walter): la interfaz queda lista para el
 * modo Videos sin rehacer nada. Hoy solo hay un modo registrado, Software, y
 * el selector Software | Videos no se pinta: pintarlo sería prometer algo que
 * no existe. El tipo de nicho es un dato y el adaptador de Software convierte
 * un veredicto del juez en un nicho genérico.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { hayQueElegirModo, MODOS, modoPorId } from "./registro.ts";
import { nichoDeSoftware } from "./software.ts";

test("hoy solo está el modo Software y el selector no se pinta", () => {
  assert.deepEqual(MODOS.map((m) => m.id), ["software"]);
  assert.equal(hayQueElegirModo(MODOS), false);
  assert.equal(modoPorId("software").id, "software");
});

test("con dos modos registrados, el selector se pinta", () => {
  const videos = { ...MODOS[0], id: "videos" as const };
  assert.equal(hayQueElegirModo([...MODOS, videos]), true);
});

const veredicto = {
  id: "v1", runId: "r1", verdict: "INVESTIGAR MÁS" as const, rule: "9: G7 con menciones favorables de menos de 3 autores",
  score: 16.5, memberCount: 9, keywords: ["facturas"],
  problemName: { es: "Tener que reclamar facturas impagadas", en: "Chasing down unpaid overdue invoices" },
  evidence: [{ id: "hackernews:1", source: "hackernews", excerpt: "I spend every Friday chasing clients", createdAt: "2026-09-20T00:00:00Z",
    attribution: { badge: "Hacker News", site: "Ask HN", url: "https://example.com/1", license: null, licenseUrl: null } }],
};

test("un veredicto del juez se convierte en un nicho de tipo software, en lenguaje llano", () => {
  const n = nichoDeSoftware(veredicto, "es");
  assert.equal(n.tipo, "software");
  assert.equal(n.id, "v1");
  assert.equal(n.nombre, "Tener que reclamar facturas impagadas");
  assert.equal(n.subnombre, "Chasing down unpaid overdue invoices");
  assert.equal(n.veredicto, "INVESTIGAR MÁS");
  assert.equal(n.porQue, "r9", "la regla 9 se explica con su frase, no con su número");
  assert.equal(n.mezcla, false);
  assert.deepEqual(n.metricas, [{ clave: "personas", valor: 9 }, { clave: "puntuacion", valor: 16.5 }]);
  assert.deepEqual(n.quejas[0], { texto: "I spend every Friday chasing clients", fuente: "Hacker News",
    url: "https://example.com/1" });
});

test("un grupo mezclado no tiene nombre propio ni puntuación", () => {
  const n = nichoDeSoftware({ ...veredicto, score: null, problemName: null }, "es");
  assert.equal(n.mezcla, true);
  assert.deepEqual(n.metricas, [{ clave: "personas", valor: 9 }]);
});

test("un grupo sin nombre de G0 se enseña con una frase de sus quejas, nunca con palabras sueltas", () => {
  // `veredicto` trae palabras («facturas»): no se enseñan.
  const n = nichoDeSoftware({ ...veredicto, problemName: null }, "es");
  assert.equal(n.nombre, "«I spend every Friday chasing clients»");
  assert.equal(n.subnombre, null);
});

test("una mezcla se nombra con una frase de sus quejas aunque G0 le diera nombre", () => {
  const n = nichoDeSoftware({ ...veredicto, score: null }, "es");
  assert.equal(n.nombre, "«I spend every Friday chasing clients»");
  assert.equal(n.subnombre, null, "G0 dice que no es un solo problema: su nombre no lo describe");
});

test("una regla que no se conoce se explica en «Ver detalle»", () => {
  assert.equal(nichoDeSoftware({ ...veredicto, rule: "42: nueva" }, "es").porQue, "otra");
});
