/**
 * Nombre y puntuación de un veredicto en pantalla.
 *
 * Un grupo mezclado (G0 fallida: «no es un mismo problema») llega con score
 * null: no tiene problema común que nombrar ni que puntuar (decisión del
 * usuario), así que se dice eso y no se pinta ninguna cifra.
 */
export interface GrupoEnPantalla {
  score: number | null;
  /** El nombre que da G0 (el mismo del dossier); sin él, una frase de sus quejas. */
  problemName?: { es: string; en: string } | null;
  /** Sus quejas: sin nombre, se enseña una de ejemplo (nunca palabras sueltas). */
  evidence?: { excerpt: string }[];
}

/** Largo máximo de la frase de ejemplo: se corta en una palabra entera. */
const MAX_EJEMPLO = 56;

/**
 * Una frase de ejemplo de las quejas de un grupo, entre comillas y cortada en
 * una palabra entera; null si no tiene quejas. Nunca la clave interna del
 * grupo: se forma con ids de piezas y el de Bluesky lleva el DID de su autor
 * (R9, escaneo 2 de la Fase 3).
 */
export function fraseDeEjemplo(evidencia: readonly { excerpt: string }[] | undefined): string | null {
  const texto = (evidencia?.[0]?.excerpt ?? "").split(/\s+/).filter(Boolean).join(" ");
  if (!texto) return null;
  if (texto.length <= MAX_EJEMPLO) return `«${texto}»`;
  const corte = texto.slice(0, MAX_EJEMPLO);
  return `«${corte.slice(0, corte.lastIndexOf(" ") > 0 ? corte.lastIndexOf(" ") : MAX_EJEMPLO)}…»`;
}

export function nombreDelGrupo(v: GrupoEnPantalla, sinProblemaComun: string, idioma: "es" | "en" = "es"): string {
  if (v.score === null) return sinProblemaComun;
  return v.problemName?.[idioma] || fraseDeEjemplo(v.evidence) || sinProblemaComun;
}

export function puntuacionDelGrupo(v: GrupoEnPantalla, plantilla: string): string | null {
  return v.score === null ? null : plantilla.replace("{score}", v.score.toFixed(1));
}
