/**
 * Vigía de errores de la interfaz (humo en Linux).
 *
 * En Windows el humo ve las excepciones y los errores de CSP por la
 * depuración remota de WebView2. WebKitWebDriver no los da, así que la
 * interfaz los apunta desde el arranque y el humo los lee al final.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { vigilarErrores } from "./vigia.ts";

const evento = (tipo: string, campos: Record<string, unknown>) => Object.assign(new Event(tipo), campos);

test("sin errores no apunta nada", () => {
  const vistos = vigilarErrores(new EventTarget());
  assert.deepEqual(vistos, { excepciones: [], csp: 0 });
});

test("una excepción sin capturar se apunta con su pila", () => {
  const ventana = new EventTarget();
  const vistos = vigilarErrores(ventana);
  const fallo = new TypeError("x is undefined");
  ventana.dispatchEvent(evento("error", { error: fallo, message: "Uncaught TypeError: x is undefined" }));
  assert.equal(vistos.excepciones.length, 1);
  assert.match(vistos.excepciones[0], /TypeError: x is undefined/);
});

test("una promesa rechazada sin capturar también cuenta", () => {
  const ventana = new EventTarget();
  const vistos = vigilarErrores(ventana);
  ventana.dispatchEvent(evento("unhandledrejection", { reason: new Error("sin red") }));
  ventana.dispatchEvent(evento("unhandledrejection", { reason: "texto suelto" }));
  assert.equal(vistos.excepciones.length, 2);
  assert.match(vistos.excepciones[0], /sin red/);
  assert.equal(vistos.excepciones[1], "texto suelto");
});

test("cada violación de CSP suma una", () => {
  const ventana = new EventTarget();
  const vistos = vigilarErrores(ventana);
  ventana.dispatchEvent(new Event("securitypolicyviolation"));
  ventana.dispatchEvent(new Event("securitypolicyviolation"));
  assert.equal(vistos.csp, 2);
  assert.deepEqual(vistos.excepciones, []);
});

test("no crece sin límite: guarda las primeras 50", () => {
  const ventana = new EventTarget();
  const vistos = vigilarErrores(ventana);
  for (let n = 0; n < 80; n++) ventana.dispatchEvent(evento("error", { message: `fallo ${n}` }));
  assert.equal(vistos.excepciones.length, 50);
  assert.equal(vistos.excepciones[0], "fallo 0");
});

test("main.tsx lo instala antes que nada: su primera importación es el vigía", async () => {
  const { readFile } = await import("node:fs/promises");
  const main = await readFile(new URL("../main.tsx", import.meta.url), "utf-8");
  const primera = main.split("\n").find((linea) => linea.startsWith("import "));
  assert.equal(primera, 'import "@/vigiaGlobal";');
});
