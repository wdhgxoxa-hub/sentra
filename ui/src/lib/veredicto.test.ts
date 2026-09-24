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
const nicho = { score: 42.25, keywords: ["spam", "dkim", "spf", "dmarc"], clusterKey: "spam#x" };
const mezcla = { score: null, keywords: ["app", "following", "class"], clusterKey: "app#y" };

test("un nicho enseña sus tres primeras palabras y su puntuación", () => {
  assert.equal(nombreDelGrupo(nicho, SIN), "spam · dkim · spf");
  assert.equal(puntuacionDelGrupo(nicho, PLANTILLA), "Puntaje 42.3/100");
});

test("una mezcla no lleva puntuación ni nombre propio: solo «sin problema común»", () => {
  assert.equal(nombreDelGrupo(mezcla, SIN), SIN);
  assert.equal(puntuacionDelGrupo(mezcla, PLANTILLA), null);
});

test("sin palabras, la clave del grupo", () => {
  assert.equal(nombreDelGrupo({ ...nicho, keywords: [] }, SIN), "spam#x");
});
