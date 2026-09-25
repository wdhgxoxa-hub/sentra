/**
 * Resultado de un escaneo: qué significa y qué hacer ahora (Fase 2, P1)
 * ====================================================================
 *
 * Todo final de escaneo acaba en un caso y en al menos un paso. Los textos
 * son claves de i18n (`t.resultado.caso`, `t.resultado.paso`). Las cifras
 * salen del resumen del juez; sin él (escaneos anteriores a la migración 019)
 * se dice que no hay detalle, no se inventan.
 *
 * Orden: cancelado, cortado por un tope de Gemini, CONSTRUIR, INVESTIGAR MÁS,
 * sin nada traído y, por último, sin nichos.
 */

import type { NicheVerdict, RunOverview } from "@/types/radar";

export type CasoDeResultado =
  | "cancelado"
  | "tope_gemini"
  | "construir"
  | "investigar"
  | "sin_piezas"
  | "cero_nichos";

export type ClaveDePaso =
  | "volver_a_escanear"
  | "subir_tope_o_esperar"
  | "leer_dossier"
  | "generar_plan"
  | "ampliar_para_confirmar"
  | "otras_palabras"
  | "mas_antiguedad"
  | "anadir_otro_idioma"
  | "mas_palabras"
  | "describir_problema"
  | "radar_sigue";

/** Adónde lleva el paso, si lleva a algún sitio. */
export type AccionDePaso = "ajustar_palabras" | "abrir_nicho" | "abrir_radar" | "abrir_configuracion";

export interface PasoSiguiente {
  clave: ClaveDePaso;
  accion: AccionDePaso | null;
}

export interface ResultadoDeEscaneo {
  escaneo: RunOverview;
  veredictos: { verdict: NicheVerdict }[];
  cancelado: boolean;
  /** Hay un escaneo anterior con nichos: el Radar lo sigue enseñando. */
  hayNichoAnterior: boolean;
}

export interface SiguientePaso {
  caso: CasoDeResultado;
  pasos: PasoSiguiente[];
  /** Piezas leídas, con dolor y personas distintas que pide un nicho; null sin resumen. */
  cifras: { leidas: number; conDolor: number; personasNecesarias: number } | null;
  /** El escaneo es anterior al resumen del juez: no hay detalle que contar. */
  sinDetalle: boolean;
}

const MINIMO_DE_PALABRAS = 6;

const ACCION: Partial<Record<ClaveDePaso, AccionDePaso>> = {
  volver_a_escanear: "ajustar_palabras",
  subir_tope_o_esperar: "abrir_configuracion",
  leer_dossier: "abrir_nicho",
  generar_plan: "abrir_nicho",
  ampliar_para_confirmar: "ajustar_palabras",
  otras_palabras: "ajustar_palabras",
  anadir_otro_idioma: "ajustar_palabras",
  mas_palabras: "ajustar_palabras",
  radar_sigue: "abrir_radar",
};

function pasos(...claves: ClaveDePaso[]): PasoSiguiente[] {
  return claves.map((clave) => ({ clave, accion: ACCION[clave] ?? null }));
}

export function siguientePaso(r: ResultadoDeEscaneo): SiguientePaso {
  const resumen = r.escaneo.summary;
  const cifras =
    resumen && resumen.pain !== undefined && resumen.minAuthors !== undefined
      ? { leidas: resumen.items, conDolor: resumen.pain, personasNecesarias: resumen.minAuthors }
      : null;
  const conCifras = (caso: CasoDeResultado, lista: PasoSiguiente[]): SiguientePaso => ({
    caso, pasos: lista, cifras, sinDetalle: cifras === null,
  });

  if (r.cancelado) return conCifras("cancelado", pasos("volver_a_escanear"));
  if (r.escaneo.stopReason?.startsWith("tope_")) return conCifras("tope_gemini", pasos("subir_tope_o_esperar"));
  if (r.veredictos.some((v) => v.verdict === "CONSTRUIR")) {
    return conCifras("construir", pasos("leer_dossier", "generar_plan"));
  }
  if (r.veredictos.some((v) => v.verdict === "INVESTIGAR MÁS")) {
    return conCifras("investigar", pasos("leer_dossier", "ampliar_para_confirmar"));
  }
  if (r.escaneo.fetched === 0) return conCifras("sin_piezas", pasos("otras_palabras", "mas_antiguedad"));

  const claves: ClaveDePaso[] = [];
  if (r.escaneo.languages.length < 2) claves.push("anadir_otro_idioma");
  if (r.escaneo.keywords.length < MINIMO_DE_PALABRAS) claves.push("mas_palabras");
  claves.push("describir_problema");
  if (r.hayNichoAnterior) claves.push("radar_sigue");
  return conCifras("cero_nichos", pasos(...claves));
}
