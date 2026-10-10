/**
 * Propuestas de Claude Desktop: «Revisar» vuelca la propuesta en el paso de
 * revisar del asistente, de modo que el perfil que se estima y se lanza es
 * el que propuso Claude (y Walter puede cambiarlo antes).
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { perfilDelAsistente } from "./encaje.ts";
import { asistenteDesdePropuesta, diasMasCercanos } from "./propuestas.ts";
import type { ScanRequestProfile } from "@/types/radar";

const propuesta: ScanRequestProfile = {
  name: "Café de especialidad",
  topic: "Tostadores pequeños que no encuentran clientes",
  topicKind: "otro",
  keywords: ["café de especialidad", "specialty coffee roaster"],
  keywordLanguages: { "café de especialidad": "es", "specialty coffee roaster": "en" },
  intents: ["frustration", "workaround"],
  languages: ["es", "en"],
  targets: { stackexchange: ["coffee"] },
  windowDays: 180,
  discovery: false,
  phraseLibraryVersion: "v1",
};

test("la propuesta llena el asistente en el paso de revisar", () => {
  const a = asistenteDesdePropuesta(propuesta);
  assert.equal(a.paso, 3);
  assert.equal(a.tema, "Tostadores pequeños que no encuentran clientes");
  assert.deepEqual(a.palabras, { es: ["café de especialidad"], en: ["specialty coffee roaster"] });
  assert.equal(a.dias, 180);
  assert.deepEqual(a.sitiosStackExchange, ["coffee"]);
});

test("lo que se estima y se lanza es el perfil que propuso Claude", () => {
  const perfil = perfilDelAsistente(asistenteDesdePropuesta(propuesta), "Nuevo escaneo");
  assert.equal(perfil.name, "Café de especialidad");
  assert.equal(perfil.topic, propuesta.topic);
  assert.equal(perfil.topicKind, "otro");
  assert.deepEqual(perfil.keywords, propuesta.keywords);
  assert.deepEqual(perfil.keywordLanguages, propuesta.keywordLanguages);
  assert.deepEqual(perfil.targets, { stackexchange: ["coffee"] });
  assert.equal(perfil.windowDays, 180);
  assert.equal(perfil.discovery, false);
});

test("un idioma con palabras se busca aunque la propuesta no lo nombre", () => {
  const a = asistenteDesdePropuesta({ ...propuesta, languages: ["en"] });
  assert.deepEqual(a.idiomas, ["es", "en"]);
  assert.deepEqual(perfilDelAsistente(a, "x").keywords, propuesta.keywords);
});

test("descubrimiento: sin tema ni palabras", () => {
  const a = asistenteDesdePropuesta({ ...propuesta, discovery: true, keywords: [], keywordLanguages: {} });
  assert.equal(a.sinTema, true);
  assert.equal(a.tema, "");
  assert.equal(perfilDelAsistente(a, "x").discovery, true);
});

test("sin frase del tema se usa el nombre", () => {
  assert.equal(asistenteDesdePropuesta({ ...propuesta, topic: "" }).tema, "Café de especialidad");
});

test("la antigüedad se ajusta a las que ofrece el asistente", () => {
  assert.equal(diasMasCercanos(30), 90);
  assert.equal(diasMasCercanos(135), 180);
  assert.equal(diasMasCercanos(3650), 365);
  assert.equal(diasMasCercanos(272), 180);
});
