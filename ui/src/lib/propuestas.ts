/**
 * Propuestas de escaneo de Claude Desktop
 * =======================================
 *
 * Claude lee SENTRA por su servidor MCP y, como mucho, propone un escaneo
 * (decisión de Walter, 2026-10-09). La propuesta llega a la ventana y
 * «Revisar» la vuelca en el asistente, en el paso de revisar: ahí se ve lo
 * que costará y solo «Escanear» la lanza, con su estimación confirmada como
 * cualquier otro escaneo. Antes de lanzarla se puede cambiar todo.
 */

import type { IdiomaDeBusqueda } from "./cobertura.ts";
import type { TipoDeTema } from "./encaje.ts";
import type { ScanRequestProfile } from "@/types/radar";

/** Antigüedades que ofrece el asistente, en días. */
export const DIAS_DEL_ASISTENTE = [90, 180, 365] as const;
export type DiasDelAsistente = (typeof DIAS_DEL_ASISTENTE)[number];

const IDIOMAS: IdiomaDeBusqueda[] = ["es", "en"];

/** Lo que la propuesta rellena del asistente. */
export interface AsistenteDesdePropuesta {
  paso: 3;
  nombre: string;
  tema: string;
  sinTema: boolean;
  palabras: Record<IdiomaDeBusqueda, string[]>;
  idiomas: IdiomaDeBusqueda[];
  dias: DiasDelAsistente;
  tipoDeTema: TipoDeTema | null;
  sitiosStackExchange: string[];
  temaDeLaPropuesta: string;
  propuesta: null;
}

/** La antigüedad del asistente más cercana a la pedida (a igual distancia, la mayor). */
export function diasMasCercanos(pedidos: number): DiasDelAsistente {
  return DIAS_DEL_ASISTENTE.reduce((mejor, d) =>
    Math.abs(d - pedidos) <= Math.abs(mejor - pedidos) ? d : mejor,
  );
}

export function asistenteDesdePropuesta(perfil: ScanRequestProfile): AsistenteDesdePropuesta {
  const sinTema = perfil.discovery;
  const tema = sinTema ? "" : (perfil.topic || perfil.name).trim();
  const idiomaDe = (p: string): IdiomaDeBusqueda => (perfil.keywordLanguages[p] === "es" ? "es" : "en");
  const palabras = {
    es: sinTema ? [] : perfil.keywords.filter((p) => idiomaDe(p) === "es"),
    en: sinTema ? [] : perfil.keywords.filter((p) => idiomaDe(p) === "en"),
  };
  // Un idioma con palabras se busca aunque la propuesta no lo nombre: si no, sus palabras se perderían.
  const pedidos = IDIOMAS.filter((i) => perfil.languages.includes(i) || palabras[i].length > 0);
  return {
    paso: 3,
    nombre: perfil.name.trim().slice(0, 60),
    tema,
    sinTema,
    palabras,
    idiomas: pedidos.length > 0 ? pedidos : [...IDIOMAS],
    dias: diasMasCercanos(perfil.windowDays),
    tipoDeTema: perfil.topicKind,
    sitiosStackExchange: perfil.targets.stackexchange ?? [],
    // El tipo de tema vale para este tema (lib/encaje.ts).
    temaDeLaPropuesta: tema,
    propuesta: null,
  };
}
