/**
 * Modos de SENTRA (Fase 2, principio P2)
 * ======================================
 *
 * Un modo es lo que cambia entre buscar nichos de software y, en el futuro,
 * de vídeos: los textos del asistente y cómo se cuenta un nicho (sus
 * métricas y el porqué de su veredicto). Las pantallas y los componentes
 * genéricos reciben un `Modo` y nichos ya adaptados (`NichoEnPantalla`); no
 * saben de dónde salen. El tipo de nicho es un dato, no está en el código.
 *
 * Cómo se enchufará Videos: `modos/videos.ts` con sus textos, métricas y su
 * adaptador; registrarlo en `modos/registro.ts` (aparece el selector de la
 * barra lateral); darle al motor sus rutas. Nada de lo de esta fase cambia.
 */

import type { Dictionary } from "@/i18n/es";
import type { NicheVerdict } from "@/types/radar";

export type TipoDeNicho = "software" | "videos";

/** Una cifra de un nicho; el modo sabe cómo se dice. */
export interface Metrica {
  clave: string;
  valor: number;
}

/** Una queja que respalda el nicho, con su fuente y su enlace. */
export interface QuejaEnPantalla {
  texto: string;
  fuente: string;
  url: string | null;
}

/** Lo que las pantallas saben de un nicho, sea del modo que sea. */
export interface NichoEnPantalla {
  id: string;
  tipo: TipoDeNicho;
  nombre: string;
  /** El nombre en el otro idioma, si lo hay. */
  subnombre: string | null;
  veredicto: NicheVerdict;
  /** Clave de la frase que explica el veredicto (`t.nicho.porQue`). */
  porQue: string;
  /** Las quejas no hablan de un mismo problema. */
  mezcla: boolean;
  metricas: Metrica[];
  quejas: QuejaEnPantalla[];
}

/** Los textos del asistente que dependen del modo. */
export interface TextosDelModo {
  nombre: string;
  pregunta: string;
  explica: string;
  ejemplo: string;
  ejemplos: string;
}

export interface Modo {
  id: TipoDeNicho;
  textos: (t: Dictionary) => TextosDelModo;
  /** Una métrica dicha en palabras («9 personas distintas»). */
  metrica: (t: Dictionary, m: Metrica) => string;
}
