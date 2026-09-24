/**
 * Nombre y puntuación de un veredicto en pantalla.
 *
 * Un grupo mezclado (G0 fallida: «no es un mismo problema») llega con score
 * null: no tiene problema común que nombrar ni que puntuar (decisión del
 * usuario), así que se dice eso y no se pinta ninguna cifra.
 */
export interface GrupoEnPantalla {
  score: number | null;
  keywords: string[];
  clusterKey: string;
}

export function nombreDelGrupo(v: GrupoEnPantalla, sinProblemaComun: string): string {
  if (v.score === null) return sinProblemaComun;
  return v.keywords.slice(0, 3).join(" · ") || v.clusterKey;
}

export function puntuacionDelGrupo(v: GrupoEnPantalla, plantilla: string): string | null {
  return v.score === null ? null : plantilla.replace("{score}", v.score.toFixed(1));
}
