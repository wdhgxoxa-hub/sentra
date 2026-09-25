/**
 * Aviso de cobertura de las palabras clave (Fase 2)
 * =================================================
 *
 * Paso 2 del asistente. Con pocas palabras, o todas en un idioma, lo normal
 * es que el juez no forme ningún nicho: el escaneo del 24-09 buscó solo
 * «facturas impagadas» y salió vacío. El aviso no bloquea; dice qué falta.
 * Reglas (decisión de Walter): menos de 6 palabras, todas en un solo idioma,
 * un idioma elegido sin palabras o con menos de 3.
 */

export type IdiomaDeBusqueda = "es" | "en";
export type MotivoDeCobertura = "pocas" | "un_idioma" | "idioma_sin_palabras" | "idioma_escaso" | "largas";

export const MINIMO_TOTAL = 6;
export const MINIMO_POR_IDIOMA = 3;
/** Fase 3: HN, Stack Exchange, Bluesky y Mastodon piden todas las palabras;
 *  GitHub, la frase exacta. Con más de 3, casi nada coincide (medido el 25-09). */
export const MAXIMO_DE_PALABRAS = 3;

export interface Cobertura {
  nivel: "buena" | "baja";
  /** En este orden: pocas, un_idioma, idioma_sin_palabras, idioma_escaso, largas. */
  motivos: MotivoDeCobertura[];
  total: number;
  porIdioma: Record<IdiomaDeBusqueda, number>;
  /** Idiomas elegidos sin ninguna palabra. */
  sinPalabras: IdiomaDeBusqueda[];
  /** Idiomas elegidos con alguna palabra, pero menos de 3. */
  escasos: IdiomaDeBusqueda[];
  /** Búsquedas de más de 3 palabras. */
  largas: string[];
}

/** Palabras distintas de una lista: sin vacías y sin repetir (mayúsculas y espacios aparte). */
export function palabrasDistintas(lista: readonly string[]): string[] {
  const vistas = new Set<string>();
  const distintas: string[] = [];
  for (const palabra of lista) {
    const limpia = palabra.trim().replace(/\s+/g, " ");
    const clave = limpia.toLowerCase();
    if (!limpia || vistas.has(clave)) continue;
    vistas.add(clave);
    distintas.push(limpia);
  }
  return distintas;
}

export function coberturaDePalabras(
  palabras: Record<IdiomaDeBusqueda, readonly string[]>,
  elegidos: readonly IdiomaDeBusqueda[],
): Cobertura {
  const porIdioma = {
    es: palabrasDistintas(palabras.es).length,
    en: palabrasDistintas(palabras.en).length,
  };
  const total = porIdioma.es + porIdioma.en;
  const conPalabras = (["es", "en"] as const).filter((i) => porIdioma[i] > 0);
  const sinPalabras = elegidos.filter((i) => porIdioma[i] === 0);
  const escasos = elegidos.filter((i) => porIdioma[i] > 0 && porIdioma[i] < MINIMO_POR_IDIOMA);

  const motivos: MotivoDeCobertura[] = [];
  if (total < MINIMO_TOTAL) motivos.push("pocas");
  if (conPalabras.length === 1) motivos.push("un_idioma");
  if (sinPalabras.length > 0) motivos.push("idioma_sin_palabras");
  if (escasos.length > 0) motivos.push("idioma_escaso");
  const largas = elegidos
    .flatMap((i) => palabrasDistintas(palabras[i]))
    .filter((p) => p.split(" ").length > MAXIMO_DE_PALABRAS);
  if (largas.length > 0) motivos.push("largas");
  return { nivel: motivos.length ? "baja" : "buena", motivos, total, porIdioma, sinPalabras, escasos, largas };
}
