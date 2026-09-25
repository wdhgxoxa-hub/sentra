/**
 * Modos registrados. Hoy solo Software: el selector Software | Videos de la
 * barra lateral no se pinta hasta que haya dos (pintarlo antes prometería
 * algo que no existe).
 */

import { modoSoftware } from "./software.ts";
import type { Modo, TipoDeNicho } from "./tipos.ts";

export const MODOS: readonly Modo[] = [modoSoftware];

export function hayQueElegirModo(modos: readonly Modo[]): boolean {
  return modos.length > 1;
}

export function modoPorId(id: TipoDeNicho): Modo {
  return MODOS.find((m) => m.id === id) ?? MODOS[0];
}
