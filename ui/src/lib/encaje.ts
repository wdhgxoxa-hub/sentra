/**
 * Fuentes según el tipo de tema (Fase 3, medida B de Walter)
 * ==========================================================
 *
 * El asistente envía el tema completo (lo recibe el etiquetador), su tipo y
 * los sitios de Stack Exchange que propuso Gemini. El motor omite lo que no
 * encaja (core/sources/encaje.py) y aquí se dice por qué, en lenguaje llano.
 * Sin propuesta de Gemini, o si el tema cambió después, no se sabe el tipo:
 * no se omite nada.
 */

import type { ScanProfileInput } from "@/types/radar";

import { palabrasDistintas, type IdiomaDeBusqueda } from "./cobertura.ts";

export type TipoDeTema = "software" | "otro";
export type MotivoDeOmision = "no_es_software" | "sin_sitio" | "otro";

/** Lo que el perfil necesita del asistente. */
export interface DatosDelAsistente {
  nombre: string;
  tema: string;
  sinTema: boolean;
  palabras: Record<IdiomaDeBusqueda, string[]>;
  idiomas: IdiomaDeBusqueda[];
  dias: number;
  tipoDeTema: TipoDeTema | null;
  sitiosStackExchange: string[];
  /** El tema con el que se pidió la propuesta: si cambió, su tipo ya no vale. */
  temaDeLaPropuesta: string;
}

export function perfilDelAsistente(a: DatosDelAsistente, nombrePorDefecto: string): ScanProfileInput {
  const tema = a.sinTema ? "" : a.tema.trim();
  const es = a.idiomas.includes("es") ? palabrasDistintas(a.palabras.es) : [];
  const en = a.idiomas.includes("en") ? palabrasDistintas(a.palabras.en) : [];
  const vigente = !a.sinTema && tema !== "" && a.temaDeLaPropuesta.trim() === tema;
  const sitios = vigente ? a.sitiosStackExchange : [];
  return {
    name: (a.nombre || a.tema || nombrePorDefecto).trim().slice(0, 60),
    topic: tema.slice(0, 200),
    topicKind: vigente ? a.tipoDeTema : null,
    ...(sitios.length > 0 ? { targets: { stackexchange: sitios } } : {}),
    keywords: a.sinTema ? [] : [...es, ...en],
    // El idioma de cada palabra es el de su fila: el motor no tiene que adivinarlo.
    keywordLanguages: a.sinTema
      ? {}
      : Object.fromEntries([...es.map((p) => [p, "es"] as const), ...en.map((p) => [p, "en"] as const)]),
    discovery: a.sinTema,
    windowDays: a.dias,
    languages: a.idiomas,
  };
}

/** El motivo de una omisión, con o sin el prefijo `omitida:` del motor. */
export function motivoDeOmision(codigo: string): MotivoDeOmision {
  const motivo = codigo.replace(/^omitida:/, "");
  return motivo === "no_es_software" || motivo === "sin_sitio" ? motivo : "otro";
}

/** Las fuentes omitidas, en orden, con su motivo. */
export function omisiones(
  omitidas: Record<string, string> | undefined,
): { fuente: string; motivo: MotivoDeOmision }[] {
  return Object.entries(omitidas ?? {})
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([fuente, codigo]) => ({ fuente, motivo: motivoDeOmision(codigo) }));
}
