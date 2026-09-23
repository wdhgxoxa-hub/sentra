/**
 * Progreso del escaneo multifuente
 * ================================
 *
 * Eventos empujados por Rust (`sources:events`) que solo existen mientras
 * dura el escaneo: Zustand y no TanStack Query, como `progressStore`.
 * Cada fuente avanza por su cuenta; el fallo de una no para a las demás, y
 * la vista lo enseña fuente a fuente.
 */

import { create } from "zustand";

import type { JudgeSummary, MultiScanEvent, SourceScanSummary } from "@/types/radar";

export interface MultiScanState {
  status: "idle" | "running" | "done" | "error";
  /** Para cancelar; null hasta `scan:started`. */
  scanId: string | null;
  runId: string | null;
  /** Orden en que las anunció el sidecar. */
  sources: string[];
  perSource: Record<string, SourceScanSummary>;
  /** Resumen final; null hasta `scan:done`. */
  final: Extract<MultiScanEvent, { type: "scan:done" }> | null;
  /** Fallo que impidió escanear (p. ej. no_active_sources). */
  error: { code: string; detail: string } | null;
  /** El juez corre tras un escaneo guardado; «idle» si no hubo juez. */
  judge: {
    status: "idle" | "running" | "done" | "error";
    summary: JudgeSummary | null;
    error: { code: string; detail: string } | null;
  };
}

export const ESCANEO_VACIO: MultiScanState = {
  status: "idle",
  scanId: null,
  runId: null,
  sources: [],
  perSource: {},
  final: null,
  error: null,
  judge: { status: "idle", summary: null, error: null },
};

function enMarcha(): SourceScanSummary {
  return {
    status: "running", items: 0, errorCode: null, detail: null, stopReason: null,
    requests: 0, units: 0, usd: 0,
  };
}

/** Aplica un evento. Puro: la vista y el almacén comparten la misma regla. */
export function reducirEscaneo(estado: MultiScanState, evento: MultiScanEvent): MultiScanState {
  const fuente = (id: string) => estado.perSource[id] ?? enMarcha();
  switch (evento.type) {
    case "scan:started":
      return {
        ...ESCANEO_VACIO,
        status: "running",
        scanId: evento.scanId,
        runId: evento.runId,
        sources: evento.sources,
        perSource: Object.fromEntries(evento.sources.map((id) => [id, enMarcha()])),
      };
    case "source:started":
      return { ...estado, perSource: { ...estado.perSource, [evento.source]: fuente(evento.source) } };
    case "source:progress":
      return {
        ...estado,
        perSource: {
          ...estado.perSource,
          [evento.source]: { ...fuente(evento.source), items: evento.items },
        },
      };
    case "source:done":
      return {
        ...estado,
        perSource: {
          ...estado.perSource,
          [evento.source]: {
            ...fuente(evento.source), status: "done", items: evento.items,
            stopReason: evento.stopReason,
          },
        },
      };
    case "source:error":
      return {
        ...estado,
        perSource: {
          ...estado.perSource,
          [evento.source]: {
            ...fuente(evento.source), status: "failed", items: evento.items,
            errorCode: evento.code, detail: evento.detail,
          },
        },
      };
    case "scan:done":
      // El resumen final manda: trae peticiones, unidades y USD de cada una.
      return { ...estado, status: "done", runId: evento.runId, perSource: evento.perSource, final: evento };
    case "judge:started":
      return { ...estado, judge: { status: "running", summary: null, error: null } };
    case "judge:done":
      return { ...estado, judge: { status: "done", summary: evento.summary, error: null } };
    case "judge:error":
      return {
        ...estado,
        judge: { status: "error", summary: null, error: { code: evento.code, detail: evento.message } },
      };
    case "error":
      return { ...estado, status: "error", error: { code: evento.code, detail: evento.message } };
  }
}

interface MultiScanStore {
  scan: MultiScanState;
  apply: (evento: MultiScanEvent) => void;
  fail: (error: { code: string; detail: string }) => void;
  reset: () => void;
}

export const useMultiscanStore = create<MultiScanStore>((set) => ({
  scan: ESCANEO_VACIO,
  apply: (evento) => set((s) => ({ scan: reducirEscaneo(s.scan, evento) })),
  fail: (error) => set((s) => ({ scan: { ...s.scan, status: "error", error } })),
  reset: () => set({ scan: ESCANEO_VACIO }),
}));
