/**
 * Aviso de cobertura de las palabras clave (Fase 2, paso 2 del asistente).
 *
 * Con pocas palabras, o todas en un solo idioma, lo normal es que el juez no
 * forme ningún nicho (escaneo del 24-09: solo «facturas impagadas» → 0
 * nichos). El aviso no bloquea: dice qué falta.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { coberturaDePalabras } from "./cobertura.ts";

const AMBOS = ["es", "en"] as const;
const seis = (prefijo: string) => Array.from({ length: 3 }, (_, n) => `${prefijo} ${n}`);

test("sin palabras, la cobertura es baja y dice que faltan", () => {
  const c = coberturaDePalabras({ es: [], en: [] }, [...AMBOS]);
  assert.equal(c.nivel, "baja");
  assert.deepEqual(c.motivos, ["pocas", "idioma_sin_palabras"]);
  assert.equal(c.total, 0);
});

test("dos palabras solo en español: pocas, un solo idioma, inglés vacío y español escaso", () => {
  const c = coberturaDePalabras({ es: ["facturas impagadas", "cliente no paga"], en: [] }, [...AMBOS]);
  assert.equal(c.nivel, "baja");
  assert.deepEqual(c.motivos, ["pocas", "un_idioma", "idioma_sin_palabras", "idioma_escaso"]);
  assert.deepEqual(c.sinPalabras, ["en"]);
  assert.deepEqual(c.escasos, ["es"]);
});

test("muchas palabras pero todas en un idioma: se avisa igual (decisión de Walter)", () => {
  const c = coberturaDePalabras({ es: [...seis("a"), ...seis("b")], en: [] }, ["es"]);
  assert.equal(c.nivel, "baja");
  assert.deepEqual(c.motivos, ["un_idioma"]);
});

test("3 y 3 en los dos idiomas: buena cobertura", () => {
  const c = coberturaDePalabras({ es: seis("es"), en: seis("en") }, [...AMBOS]);
  assert.equal(c.nivel, "buena");
  assert.deepEqual(c.motivos, []);
  assert.deepEqual(c.porIdioma, { es: 3, en: 3 });
});

test("un idioma elegido con menos de 3 palabras es escaso", () => {
  const c = coberturaDePalabras({ es: [...seis("a"), "x"], en: ["unpaid invoices", "late payment"] }, [...AMBOS]);
  assert.deepEqual(c.motivos, ["idioma_escaso"]);
  assert.deepEqual(c.escasos, ["en"]);
});

test("las repetidas y las vacías no cuentan", () => {
  const c = coberturaDePalabras(
    { es: ["Facturas", " facturas ", "", "cobros", "pagos"], en: ["a", "A", "b", "c"] },
    [...AMBOS],
  );
  assert.deepEqual(c.porIdioma, { es: 3, en: 3 });
  assert.equal(c.total, 6);
  assert.equal(c.nivel, "buena");
});

test("Fase 3: las búsquedas de más de 3 palabras se señalan (los buscadores piden todas a la vez)", () => {
  const c = coberturaDePalabras(
    { es: ["pdf a word", "convertir pdf", "pdf a word pierde formato"], en: ["pdf to word", "pdf converter", "docx"] },
    ["es", "en"],
  );
  assert.deepEqual(c.motivos, ["largas"]);
  assert.deepEqual(c.largas, ["pdf a word pierde formato"]);
  assert.equal(c.nivel, "baja");
});
