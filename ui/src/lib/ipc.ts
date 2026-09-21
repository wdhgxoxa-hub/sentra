/**
 * Puente tipado con Rust
 * ======================
 *
 * Unico punto donde se escriben los nombres de los comandos. Ningun
 * componente llama a `invoke` con cadenas sueltas: un nombre mal escrito
 * debe ser un error de compilacion, no un fallo en tiempo de ejecucion.
 *
 * Cada comando indica quien lo resuelve:
 *   [pg]      Rust contra PostgreSQL.
 *   [sidecar] Rust reenvia al proceso Python por HTTP local.
 *
 * Pendientes de implementar en Rust (deuda D17), por eso NO se declaran
 * aqui: update_opportunity_status, upsert_subreddit y cancel_scan.
 * Declararlos sin backend solo produciria fallos en tiempo de ejecucion.
 */

import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

import {
  RADAR_EVENT_CHANNEL,
  type AppHealth,
  type BoardParams,
  type ClusterHistoryPoint,
  type FeedParams,
  type HybridSearchHit,
  type OpportunityCluster,
  type PipelineRun,
  type RadarEvent,
  type RadarFeedEntry,
  type ScanParams,
  type SearchParams,
  type SubredditHealth,
} from "@/types/radar";

export const ipc = {
  /** [pg] Senales individuales que superaron el filtro de higiene. */
  getRadarFeed: (params: FeedParams = {}) =>
    invoke<RadarFeedEntry[]>("get_radar_feed", { params }),

  /** [pg] Problemas recurrentes consolidados. */
  getOpportunityBoard: (params: BoardParams = {}) =>
    invoke<OpportunityCluster[]>("get_opportunity_board", { params }),

  /** [pg] Ficha de una oportunidad: la lectura mas reciente de esa clave. */
  getOpportunityDetail: (clusterKey: string) =>
    invoke<OpportunityCluster | null>("get_opportunity_detail", { clusterKey }),

  /** [pg] Lecturas sucesivas del mismo problema, para ver como evoluciona. */
  getClusterHistory: (clusterKey: string) =>
    invoke<ClusterHistoryPoint[]>("get_cluster_history", { clusterKey }),

  /** [pg] Subreddits vigilados con el resultado de su ultimo escaneo. */
  getSubreddits: () => invoke<SubredditHealth[]>("get_subreddits"),

  /** [pg] Telemetria de las ultimas ejecuciones del grafo. */
  getPipelineRuns: (limit = 50) =>
    invoke<PipelineRun[]>("get_pipeline_runs", { limit }),

  /** [sidecar] Busqueda hibrida densa + BM25 con fusion RRF. */
  searchHybrid: (params: SearchParams) =>
    invoke<HybridSearchHit[]>("search_hybrid", { params }),

  /**
   * [sidecar] Escaneo completo. Puede tardar minutos.
   *
   * El avance llega por `onRadarEvent`; lo que devuelve la promesa es el
   * ultimo evento del flujo (`run:finished` o `run:error`).
   */
  triggerScan: (params: ScanParams) =>
    invoke<RadarEvent>("trigger_scan", { params }),

  /** [pg + sidecar] Estado de las tres piezas por separado. */
  getAppHealth: () => invoke<AppHealth>("get_app_health"),
} as const;

/**
 * Se suscribe al progreso de las ejecuciones.
 *
 * El backend empuja los avances en lugar de que la interfaz pregunte: un
 * escaneo puede durar minutos y sondearlo seria ruido constante.
 */
export function onRadarEvent(
  handler: (event: RadarEvent) => void,
): Promise<UnlistenFn> {
  return listen<RadarEvent>(RADAR_EVENT_CHANNEL, (message) =>
    handler(message.payload),
  );
}
