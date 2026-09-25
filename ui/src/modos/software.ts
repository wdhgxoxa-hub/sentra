/**
 * Modo Software: nichos de software a partir de los veredictos del juez.
 *
 * `nichoDeSoftware` es el único sitio que conoce la forma de un veredicto;
 * las pantallas reciben el `NichoEnPantalla` que devuelve.
 */

import type { JudgeVerdict } from "@/types/radar";

import type { Modo, NichoEnPantalla } from "./tipos.ts";

/** Lo que el adaptador lee de un veredicto. */
export type VeredictoParaNicho = Pick<
  JudgeVerdict,
  "id" | "verdict" | "rule" | "score" | "memberCount" | "problemName" | "keywords" | "clusterKey" | "evidence"
>;

/** Cuántas quejas se enseñan de muestra. */
const QUEJAS_DE_MUESTRA = 3;
/** Reglas de la tabla del juez con su frase en `t.nicho.porQue` (r1…r9). */
const REGLAS_CONOCIDAS = 9;

function porQue(regla: string): string {
  const numero = Number(/^\s*(\d+)/.exec(regla)?.[1]);
  return numero >= 1 && numero <= REGLAS_CONOCIDAS ? `r${numero}` : "otra";
}

export function nichoDeSoftware(v: VeredictoParaNicho, idioma: "es" | "en"): NichoEnPantalla {
  const otro = idioma === "es" ? "en" : "es";
  const mezcla = v.score === null;
  const nombre = v.problemName?.[idioma] || v.keywords.slice(0, 3).join(" · ") || v.clusterKey;
  const subnombre = v.problemName?.[otro] && v.problemName[otro] !== nombre ? v.problemName[otro] : null;
  return {
    id: v.id,
    tipo: "software",
    nombre,
    subnombre,
    veredicto: v.verdict,
    porQue: porQue(v.rule),
    mezcla,
    metricas: [
      { clave: "personas", valor: v.memberCount },
      ...(v.score === null ? [] : [{ clave: "puntuacion", valor: v.score }]),
    ],
    quejas: v.evidence.slice(0, QUEJAS_DE_MUESTRA).map((e) => ({
      texto: e.excerpt,
      fuente: e.attribution.badge,
      url: e.attribution.url || null,
    })),
  };
}

export const modoSoftware: Modo = {
  id: "software",
  textos: (t) => t.modos.software,
  metrica: (t, m) =>
    m.clave === "personas"
      ? t.modos.software.personas.replace("{n}", String(m.valor))
      : t.modos.software.puntuacion.replace("{n}", m.valor.toFixed(1)),
};
