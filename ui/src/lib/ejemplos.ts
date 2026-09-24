/**
 * Ejemplos de búsqueda sacados de los nichos reales (AUD2-007)
 * ===========================================================
 *
 * Dos palabras clave de cada veredicto, sin repetir, en el orden del juez.
 * Sin veredictos no hay ejemplos: los fijos de la demostración antigua
 * («Facturación rota») no encontraban nada pertinente en el corpus real.
 */

export const MAX_EJEMPLOS = 4;

export function ejemplosDeBusqueda(veredictos: ReadonlyArray<{ keywords: readonly string[] }>): string[] {
  const vistos = new Set<string>();
  for (const { keywords } of veredictos) {
    const ejemplo = keywords.slice(0, 2).join(" ").trim();
    if (ejemplo) vistos.add(ejemplo);
    if (vistos.size === MAX_EJEMPLOS) break;
  }
  return [...vistos];
}
