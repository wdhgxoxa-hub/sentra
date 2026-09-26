/**
 * Fuentes según el tipo de tema (Fase 3, medida B de Walter): el asistente
 * envía el tema completo, su tipo y los sitios de Stack Exchange que propuso
 * Gemini; lo que no encaja se omite y se dice en lenguaje llano.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { motivoDeOmision, omisiones, perfilDelAsistente, type DatosDelAsistente } from "./encaje.ts";

const asistente: DatosDelAsistente = {
  nombre: "",
  tema: "  Perseguir a los clientes para que manden sus documentos al contable ",
  sinTema: false,
  palabras: { es: ["documentos contabilidad"], en: ["chase client documents"] },
  idiomas: ["es", "en"],
  dias: 365,
  tipoDeTema: "otro",
  sitiosStackExchange: ["money"],
  temaDeLaPropuesta: "Perseguir a los clientes para que manden sus documentos al contable",
};

test("el perfil lleva el tema completo, su tipo y los sitios de Stack Exchange", () => {
  const p = perfilDelAsistente(asistente, "Nuevo escaneo");
  assert.equal(p.topic, "Perseguir a los clientes para que manden sus documentos al contable");
  assert.equal(p.topicKind, "otro");
  assert.deepEqual(p.targets, { stackexchange: ["money"] });
  assert.equal(p.name, "Perseguir a los clientes para que manden sus documentos al c");
  assert.deepEqual(p.keywords, ["documentos contabilidad", "chase client documents"]);
});

test("sin propuesta de Gemini no se sabe el tipo ni hay sitios: no se omite nada", () => {
  const p = perfilDelAsistente({ ...asistente, tipoDeTema: null, sitiosStackExchange: [] }, "Nuevo escaneo");
  assert.equal(p.topicKind, null);
  assert.equal(p.targets, undefined);
});

test("si el tema cambió después de la propuesta, su tipo y sus sitios ya no valen", () => {
  const p = perfilDelAsistente({ ...asistente, tema: "Convertir un PDF a Word" }, "Nuevo escaneo");
  assert.equal(p.topicKind, null);
  assert.equal(p.targets, undefined);
});

test("en descubrimiento no hay tema ni tipo", () => {
  const p = perfilDelAsistente({ ...asistente, sinTema: true }, "Nuevo escaneo");
  assert.equal(p.discovery, true);
  assert.deepEqual(p.keywords, []);
  assert.equal(p.topic, "");
  assert.equal(p.topicKind, null);
});

test("el motivo de una omisión, con o sin el prefijo del motor", () => {
  assert.equal(motivoDeOmision("omitida:no_es_software"), "no_es_software");
  assert.equal(motivoDeOmision("sin_sitio"), "sin_sitio");
  assert.equal(motivoDeOmision("omitida:algo_nuevo"), "otro");
});

test("las omisiones, en orden y con su motivo", () => {
  assert.deepEqual(omisiones({ stackexchange: "omitida:sin_sitio", github: "omitida:no_es_software" }), [
    { fuente: "github", motivo: "no_es_software" },
    { fuente: "stackexchange", motivo: "sin_sitio" },
  ]);
  assert.deepEqual(omisiones(undefined), []);
});
