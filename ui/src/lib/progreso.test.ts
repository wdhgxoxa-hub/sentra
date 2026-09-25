/**
 * Progreso por fuente en palabras de todos los días (Fase 2, P1).
 *
 * Cada estado del escaneo de una fuente se convierte en un tono, un icono,
 * una palabra corta y una frase. La frase es una clave de i18n, no texto, y
 * nada depende solo del color: siempre hay palabra e icono. Un código que no
 * se conoce no se oculta; queda para «Ver detalle».
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { estadoDeFuente } from "./progreso.ts";

const base = { items: 12, errorCode: null, detail: null, stopReason: null, requests: 3, units: 0, usd: 0 };
const enCurso = { ...base, status: "running" as const };
const lista = { ...base, status: "done" as const };
const fallo = (code: string) => ({ ...base, status: "failed" as const, errorCode: code, detail: "detalle" });
const parada = (motivo: string) => ({ ...lista, stopReason: motivo });

test("buscando y listo", () => {
  assert.deepEqual(estadoDeFuente(enCurso), {
    tono: "en_curso", icono: "reloj", palabra: "buscando", frase: "buscando", items: 12, codigo: null,
  });
  assert.deepEqual(estadoDeFuente(lista), {
    tono: "bien", icono: "hecho", palabra: "lista", frase: "lista", items: 12, codigo: null,
  });
});

test("cancelada por la persona: se guarda lo traído", () => {
  const e = estadoDeFuente(parada("cancelled"));
  assert.deepEqual([e.tono, e.palabra, e.frase], ["neutro", "cancelada", "cancelada"]);
});

test("llegó al límite que pusimos para no gastar de más: termina bien, con lo traído", () => {
  const e = estadoDeFuente(parada("source_budget_exhausted"));
  assert.deepEqual([e.tono, e.palabra, e.frase], ["aviso", "parcial", "tope_propio"]);
});

const FALLOS: [string, string, string][] = [
  ["source_rate_limited", "aviso", "pidio_esperar"],
  ["source_credentials_missing", "mal", "falta_cuenta"],
  ["source_auth_failed", "mal", "clave_no_funciona"],
  ["source_forbidden", "mal", "rechazo"],
  ["source_not_found", "mal", "rechazo"],
  ["source_unavailable", "mal", "no_respondio"],
  ["source_error", "mal", "no_respondio"],
  ["internal_error", "mal", "no_respondio"],
  ["source_pending_approval", "neutro", "pendiente_aprobacion"],
];

for (const [codigo, tono, frase] of FALLOS) {
  test(`${codigo} se dice como «${frase}»`, () => {
    const e = estadoDeFuente(fallo(codigo));
    assert.equal(e.tono, tono);
    assert.equal(e.frase, frase);
    assert.equal(e.codigo, codigo, "el código queda para «Ver detalle»");
  });
}

test("un código desconocido no se oculta: «inesperado» y el código aparte", () => {
  const e = estadoDeFuente(fallo("algo_nuevo"));
  assert.deepEqual([e.tono, e.palabra, e.frase, e.codigo], ["mal", "fallo", "inesperado", "algo_nuevo"]);
});

test("una parada desconocida tampoco: parcial, con el código aparte", () => {
  const e = estadoDeFuente(parada("otra_cosa"));
  assert.deepEqual([e.tono, e.frase, e.codigo], ["aviso", "parada_antes", "otra_cosa"]);
});

test("nada depende solo del color: todo estado tiene palabra e icono", () => {
  const todos = [enCurso, lista, parada("cancelled"), parada("x"), ...FALLOS.map(([c]) => fallo(c)), fallo("y")];
  for (const s of todos) {
    const e = estadoDeFuente(s);
    assert.ok(e.palabra && e.icono, JSON.stringify(e));
  }
});
