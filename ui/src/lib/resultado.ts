/**
 * Resultado de un escaneo (Fase 2)
 * ================================
 *
 * - `marcaTrasEvento`: D3 de Walter. Si el escaneo termina mientras la
 *   persona está en otra pantalla, «Nuevo escaneo» lleva una marca. Termina
 *   con el juez (si se guardó) o con el propio escaneo (si no se guardó).
 * - `repartirVeredictos`: nichos (CONSTRUIR, INVESTIGAR MÁS) y descartados,
 *   en el orden del juez.
 * - `tonoDelCaso`: el color del aviso de cada final; el título lleva siempre
 *   la palabra, así que nada depende solo del color.
 */

import type { TonoDeAviso } from "@/components/comunes/tonos";
import type { NicheVerdict } from "@/types/radar";

import type { CasoDeResultado } from "./siguientePaso.ts";

export function marcaTrasEvento(evento: { type: string; persisted?: boolean }, vista: string): boolean {
  if (vista === "nuevo") return false;
  if (evento.type === "judge:done" || evento.type === "judge:error" || evento.type === "error") return true;
  return evento.type === "scan:done" && evento.persisted === false;
}

export function repartirVeredictos<V extends { verdict: NicheVerdict }>(
  top: readonly V[],
  resto: readonly V[],
): { nichos: V[]; descartados: V[] } {
  const todos = [...top, ...resto];
  return {
    nichos: todos.filter((v) => v.verdict !== "DESCARTAR"),
    descartados: todos.filter((v) => v.verdict === "DESCARTAR"),
  };
}

const TONOS: Record<CasoDeResultado, TonoDeAviso> = {
  construir: "bien",
  investigar: "info",
  cero_nichos: "aviso",
  sin_piezas: "aviso",
  tope_gemini: "mal",
  cancelado: "info",
};

export function tonoDelCaso(caso: CasoDeResultado): TonoDeAviso {
  return TONOS[caso];
}
