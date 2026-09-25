/**
 * Aviso del Radar (Fase 2)
 * ========================
 *
 * El Radar enseña el último escaneo con nichos. Si hubo otro después que no
 * formó ninguno, se dice cuál y cuándo: los nichos que se ven no son de ese
 * último escaneo (AUD2-001).
 */

import type { JudgeTop } from "@/types/radar";

export interface AvisoDelUltimoEscaneo {
  runId: string;
  nombre: string;
  fecha: string;
}

export function avisoDelUltimoEscaneo(top: Pick<JudgeTop, "run" | "latestRun">): AvisoDelUltimoEscaneo | null {
  const ultimo = top.latestRun;
  if (!ultimo || ultimo.runId === top.run?.runId) return null;
  return { runId: ultimo.runId, nombre: ultimo.name, fecha: ultimo.startedAt };
}
