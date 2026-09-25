/**
 * Nombre y puntuación de un veredicto en pantalla.
 *
 * Decisión del usuario: un grupo mezclado (G0 fallida: «no es un mismo
 * problema») no lleva puntuación, solo «sin problema común». El motor lo
 * guarda con score null; aquí se decide qué se pinta.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { nombreDelGrupo, puntuacionDelGrupo } from "./veredicto.ts";

const SIN = "Sin problema común";
const PLANTILLA = "Puntaje {score}/100";
const QUEJA = { excerpt: "Every month I chase clients for their receipts and bank statements by email" };
const nicho = { score: 42.25, keywords: ["spam", "dkim", "spf", "dmarc"], evidence: [QUEJA] };
const mezcla = { score: null, keywords: ["app", "following", "class"], evidence: [QUEJA] };

const FRASE = "«Every month I chase clients for their receipts and bank…»";

test("un grupo sin nombre de G0 enseña una frase de sus quejas, nunca palabras sueltas (Fase 3)", () => {
  assert.equal(nombreDelGrupo(nicho, SIN), FRASE);
  assert.equal(puntuacionDelGrupo(nicho, PLANTILLA), "Puntaje 42.3/100");
});

test("una mezcla no lleva puntuación ni nombre propio: solo «sin problema común»", () => {
  assert.equal(nombreDelGrupo(mezcla, SIN), SIN);
  assert.equal(puntuacionDelGrupo(mezcla, PLANTILLA), null);
});

test("con nombre de G0, el Radar enseña el mismo que el dossier, en su idioma", () => {
  const nombrado = { ...nicho, problemName: { es: "Perseguir facturas impagadas", en: "Chasing unpaid invoices" } };
  assert.equal(nombreDelGrupo(nombrado, SIN, "es"), "Perseguir facturas impagadas");
  assert.equal(nombreDelGrupo(nombrado, SIN, "en"), "Chasing unpaid invoices");
  assert.equal(nombreDelGrupo({ ...mezcla, problemName: nombrado.problemName }, SIN, "es"), SIN);
});

test("sin nombre ni quejas, «sin problema común»; nunca la clave interna (R9: lleva ids de piezas)", () => {
  assert.equal(nombreDelGrupo({ ...nicho, evidence: [] }, SIN), SIN);
});
