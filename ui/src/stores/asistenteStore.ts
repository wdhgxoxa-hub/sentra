/**
 * Asistente «Nuevo escaneo» (Fase 2)
 * ==================================
 *
 * Lo que la persona va escribiendo en los tres pasos. Vive aquí y no en la
 * pantalla para que cambiar de sección a mitad no lo borre.
 */

import { create } from "zustand";

import type { IdiomaDeBusqueda } from "@/lib/cobertura";
import type { TipoDeTema } from "@/lib/encaje";
import type { KeywordProposal } from "@/types/radar";

export type PasoDelAsistente = 1 | 2 | 3;
export const DIAS = [90, 180, 365] as const;
export type Dias = (typeof DIAS)[number];

interface AsistenteState {
  paso: PasoDelAsistente;
  tema: string;
  idiomas: IdiomaDeBusqueda[];
  dias: Dias;
  /** Buscar quejas de cualquier tema, sin palabras clave (modo descubrimiento). */
  sinTema: boolean;
  palabras: Record<IdiomaDeBusqueda, string[]>;
  /** De dónde salieron las últimas propuestas (null si no se pidió ninguna). */
  propuesta: Pick<KeywordProposal, "origin" | "reason"> | null;
  /** Medida B (Fase 3): de la propuesta de Gemini; valen solo para `temaDeLaPropuesta`. */
  tipoDeTema: TipoDeTema | null;
  sitiosStackExchange: string[];
  temaDeLaPropuesta: string;
  nombre: string;
  /** Hay un resultado que la persona aún no ha visto (D3: la marca). */
  resultadoSinVer: boolean;
  set: (cambios: Partial<Omit<AsistenteState, "set" | "reiniciar">>) => void;
  reiniciar: () => void;
}

const INICIAL = {
  paso: 1 as PasoDelAsistente,
  tema: "",
  idiomas: ["es", "en"] as IdiomaDeBusqueda[],
  dias: 365 as Dias,
  sinTema: false,
  palabras: { es: [], en: [] },
  propuesta: null,
  tipoDeTema: null,
  sitiosStackExchange: [],
  temaDeLaPropuesta: "",
  nombre: "",
  resultadoSinVer: false,
};

export const useAsistenteStore = create<AsistenteState>((set) => ({
  ...INICIAL,
  set: (cambios) => set(cambios),
  reiniciar: () => set(INICIAL),
}));
