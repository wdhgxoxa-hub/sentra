/**
 * Progreso de los escaneos en curso
 * =================================
 *
 * Vive en Zustand y no en TanStack Query porque no es caché de nada: son
 * eventos empujados por Rust que existen solo mientras dura la ejecución.
 * No hay a quién preguntarle por ellos.
 */

import { create } from "zustand";

import {
  PIPELINE_NODES,
  type PipelineNode,
  type RadarEvent,
  type RunStats,
} from "@/types/radar";

export interface ScanProgress {
  runId: string;
  subreddit: string;
  /** Nodos ya completados, en orden de llegada. */
  completed: PipelineNode[];
  currentNode: PipelineNode | null;
  cycle: number;
  stats: RunStats;
  status: "running" | "finished" | "error";
  message: string | null;
  qualified: number | null;
  clusters: number | null;
  startedAt: number;
}

interface ProgressState {
  /** Escaneos por runId. Puede haber varios a la vez. */
  runs: Record<string, ScanProgress>;
  apply: (event: RadarEvent) => void;
  clear: (runId: string) => void;
  clearFinished: () => void;
}

/** Fracción completada, para pintar la barra. */
export function completionRatio(progress: ScanProgress): number {
  if (progress.status === "finished") return 1;
  return progress.completed.length / PIPELINE_NODES.length;
}

export const useProgressStore = create<ProgressState>((set) => ({
  runs: {},

  apply: (event) =>
    set((state) => {
      const previous = state.runs[event.runId];

      if (event.type === "run:started") {
        return {
          runs: {
            ...state.runs,
            [event.runId]: {
              runId: event.runId,
              subreddit: event.subreddit,
              completed: [],
              currentNode: null,
              cycle: 1,
              stats: {},
              status: "running",
              message: null,
              qualified: null,
              clusters: null,
              startedAt: Date.now(),
            },
          },
        };
      }

      // Un evento de un escaneo que no se vio empezar no tiene contexto que
      // actualizar; se ignora en lugar de inventar una entrada a medias.
      if (!previous) return state;

      if (event.type === "run:progress") {
        // El grafo es cíclico: un mismo nodo se repite en cada vuelta, y
        // contarlo dos veces dispararía la barra por encima del 100 %.
        const completed = previous.completed.includes(event.node)
          ? previous.completed
          : [...previous.completed, event.node];

        return {
          runs: {
            ...state.runs,
            [event.runId]: {
              ...previous,
              completed,
              currentNode: event.node,
              cycle: event.cycle,
              stats: { ...previous.stats, ...event.stats },
            },
          },
        };
      }

      if (event.type === "run:finished") {
        return {
          runs: {
            ...state.runs,
            [event.runId]: {
              ...previous,
              status: "finished",
              currentNode: null,
              stats: { ...previous.stats, ...event.stats },
              qualified: event.qualified,
              clusters: event.clusters,
              message: event.persistError
                ? `Cosecha completa, pero no se pudo guardar: ${event.persistError}`
                : null,
            },
          },
        };
      }

      return {
        runs: {
          ...state.runs,
          [event.runId]: {
            ...previous,
            status: "error",
            currentNode: null,
            message: event.message,
          },
        },
      };
    }),

  clear: (runId) =>
    set((state) => {
      const { [runId]: _removed, ...rest } = state.runs;
      return { runs: rest };
    }),

  clearFinished: () =>
    set((state) => ({
      runs: Object.fromEntries(
        Object.entries(state.runs).filter(([, run]) => run.status === "running"),
      ),
    })),
}));
