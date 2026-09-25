/** Rellena una plantilla de i18n: cada {clave} con su valor; las que no conoce las deja. */
export function rellenar(plantilla: string, valores: Record<string, string | number>): string {
  return plantilla.replace(/\{(\w+)\}/g, (marca, clave: string) =>
    clave in valores ? String(valores[clave]) : marca,
  );
}

/** Une nombres de idioma en una frase con su nexo (« ni en », « y en »). */
export function unirIdiomas(nombres: readonly string[], nexo: string): string {
  return nombres.join(nexo);
}
