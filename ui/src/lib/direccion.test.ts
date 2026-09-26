/**
 * D-M12 (Walter, Fase 3): la dirección del original se guarda completa, con
 * el DID de Bluesky, porque sin ella no se puede verificar la evidencia (R5).
 * Pero la cuenta del autor nunca se ve como texto (R9): la dirección visible
 * va acortada y la completa solo viaja como destino de «Copiar dirección».
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { direccionVisible } from "./direccion.ts";

const BSKY = "https://bsky.app/profile/did:plc:z2gdgxz2um3eq47a2ebsz3wz/post/3mwcxhai7ay2q";

test("Bluesky: sin la cuenta, con el post", () => {
  assert.equal(direccionVisible(BSKY), "bsky.app/profile/…/post/3mwcxhai7ay2q");
});

test("Bluesky con @usuario en lugar del DID: tampoco se ve", () => {
  assert.equal(direccionVisible("https://bsky.app/profile/ana.bsky.social/post/3m"), "bsky.app/profile/…/post/3m");
});

test("cualquier tramo que lleve un DID o sea un @usuario se oculta", () => {
  assert.equal(direccionVisible("https://ejemplo.org/@ana/123"), "ejemplo.org/…/123");
  assert.equal(direccionVisible("https://ejemplo.org/x/did:web:ana.dev/y"), "ejemplo.org/x/…/y");
  assert.equal(direccionVisible("https://ejemplo.org/bluesky:did:plc:abc/3m"), "ejemplo.org/…/3m");
});

test("las demás direcciones se ven enteras, sin el protocolo", () => {
  assert.equal(direccionVisible("https://stackoverflow.com/q/2"), "stackoverflow.com/q/2");
  assert.equal(direccionVisible("https://mastodon.social/statuses/115"), "mastodon.social/statuses/115");
});

test("lo que no es una dirección se deja tal cual", () => {
  assert.equal(direccionVisible("no es una url"), "no es una url");
});
