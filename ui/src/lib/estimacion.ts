/**
 * Pantalla de confirmación antes de escanear (Fase 1, B4)
 * ======================================================
 *
 * El motor estima un rango de llamadas y tokens de Gemini (antes de escanear
 * no se sabe cuántas piezas pasarán el filtro), lo gastado hoy y lo que queda.
 * Aquí solo se da forma a esas cifras y se decide si se puede confirmar.
 */

import type { ScanEstimateDetail } from "@/types/radar";

type Idioma = "es" | "en";

/** Miles agrupados siempre (también con 4 cifras), sin depender del ICU del entorno. */
function numero(valor: number, idioma: Idioma): string {
  return String(Math.round(valor)).replace(/\B(?=(\d{3})+(?!\d))/g, idioma === "es" ? "." : ",");
}

function rango(min: number, max: number, idioma: Idioma): string {
  return min === max ? numero(max, idioma) : `${numero(min, idioma)}–${numero(max, idioma)}`;
}

export function cifrasDeLaEstimacion(e: ScanEstimateDetail, idioma: Idioma) {
  return {
    llamadas: rango(e.calls.min, e.calls.max, idioma),
    tokens: rango(e.tokens.min, e.tokens.max, idioma),
    gastadoLlamadas: numero(e.spentToday.calls, idioma),
    gastadoTokens: numero(e.spentToday.tokens, idioma),
    quedaLlamadas: numero(e.leftToday.calls, idioma),
    quedaTokens: numero(e.leftToday.tokens, idioma),
  };
}

/** Solo se confirma si hoy queda presupuesto y el escaneo podría hacer alguna llamada. */
export function sePuedeConfirmar(e: ScanEstimateDetail): boolean {
  return e.canScan && e.calls.max > 0;
}
