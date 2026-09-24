/**
 * Cuánto hace de una fecha ISO, en el idioma de la interfaz (AUD2-019).
 * Sin fecha o con una ilegible devuelve null: mejor no decir nada que
 * inventar una hora.
 */
const UNIDADES: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
];

export function haceCuanto(iso: string | null | undefined, ahora: Date, idioma: string): string | null {
  const ms = iso ? Date.parse(iso) : Number.NaN;
  if (Number.isNaN(ms)) return null;
  const formato = new Intl.RelativeTimeFormat(idioma, { numeric: "auto" });
  const segundos = Math.max(0, (ahora.getTime() - ms) / 1000);
  for (const [unidad, tamano] of UNIDADES) {
    if (segundos >= tamano) return formato.format(-Math.floor(segundos / tamano), unidad);
  }
  return formato.format(0, "second");
}
