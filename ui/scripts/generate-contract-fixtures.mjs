#!/usr/bin/env node
/**
 * Fixtures de contrato a partir de `src/types/radar.ts` (AUD-029).
 *
 * Extrae, con el propio compilador de TypeScript, las claves de cada interfaz
 * y de cada variante de las uniones discriminadas por `type`. Los tests de
 * contrato de Rust (src-tauri/src/commands/contract_tests.rs) y de Python
 * (tests/test_contracts.py) comparan lo que serializa cada capa contra este
 * JSON, así que un campo renombrado en un lado sin el otro rompe un test en
 * lugar de llegar a la interfaz como `undefined`.
 *
 *   node scripts/generate-contract-fixtures.mjs          regenera el JSON
 *   node scripts/generate-contract-fixtures.mjs --check  falla si está desfasado
 */

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import ts from "typescript";

const aqui = dirname(fileURLToPath(import.meta.url));
const ORIGEN = resolve(aqui, "../src/types/radar.ts");
const DESTINO = resolve(aqui, "../src-tauri/contract/ts_types.json");

const fuente = ts.createSourceFile(
  ORIGEN,
  readFileSync(ORIGEN, "utf8"),
  ts.ScriptTarget.Latest,
  true,
);

const nombreDe = (miembro) =>
  miembro.name && (ts.isIdentifier(miembro.name) || ts.isStringLiteral(miembro.name))
    ? miembro.name.text
    : null;

const clavesDe = (miembros) =>
  miembros
    .filter(ts.isPropertySignature)
    .map(nombreDe)
    .filter(Boolean)
    .sort();

const interfaces = {};
const uniones = {};

for (const nodo of fuente.statements) {
  if (ts.isInterfaceDeclaration(nodo)) {
    interfaces[nodo.name.text] = clavesDe(nodo.members);
  }
  // Uniones de literales de objeto discriminadas por `type` (RadarEvent).
  if (ts.isTypeAliasDeclaration(nodo) && ts.isUnionTypeNode(nodo.type)) {
    const variantes = {};
    for (const miembro of nodo.type.types) {
      // Una variante es un literal de objeto, o su intersección con una
      // interfaz del mismo archivo que aporta los campos comunes:
      // `({ type: "run:cancelled" } & RunClosedFields)`.
      const partes = ts.isIntersectionTypeNode(miembro)
        ? miembro.types
        : ts.isParenthesizedTypeNode(miembro) && ts.isIntersectionTypeNode(miembro.type)
          ? miembro.type.types
          : [miembro];
      const literal = partes.find(ts.isTypeLiteralNode);
      if (!literal) continue;
      const tipo = literal.members.find((m) => nombreDe(m) === "type");
      if (!tipo?.type || !ts.isLiteralTypeNode(tipo.type)) continue;
      const claves = new Set(clavesDe(literal.members));
      for (const parte of partes) {
        if (!ts.isTypeReferenceNode(parte)) continue;
        const comunes = interfaces[parte.typeName.getText(fuente)];
        if (!comunes) throw new Error(`Interfaz no declarada antes de la unión: ${parte.typeName.getText(fuente)}`);
        for (const clave of comunes) claves.add(clave);
      }
      variantes[tipo.type.literal.text] = [...claves].sort();
    }
    if (Object.keys(variantes).length > 0) uniones[nodo.name.text] = variantes;
  }
}

const json = `${JSON.stringify({ origen: "ui/src/types/radar.ts", interfaces, uniones }, null, 2)}\n`;

if (process.argv.includes("--check")) {
  const actual = readFileSync(DESTINO, "utf8").replace(/\r\n/g, "\n");
  if (actual !== json) {
    console.error("contract/ts_types.json está desfasado: ejecuta `npm run contracts`.");
    process.exit(1);
  }
  console.log("contract/ts_types.json al día.");
} else {
  writeFileSync(DESTINO, json);
  console.log(`Escrito ${DESTINO}`);
}
