/**
 * Puente tipado con Rust
 * ======================
 *
 * Único punto donde se escriben los nombres de los comandos. Ningún
 * componente llama a `invoke` con cadenas sueltas: un nombre mal escrito
 * debe ser un error de compilación, no un fallo en tiempo de ejecución.
 */

import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

import {
  RADAR_EVENT_CHANNEL,
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
  type UpsertSubredditParams,
  type ValidationStatus,
} from "@/types/radar";

export const ipc = {
  // --- Lecturas: Rust las resuelve contra PostgreSQL con sqlx ---

  getRadarFeed: (params: FeedParams = {}) =>
    invoke<RadarFeedEntry[]>("get_radar_feed", { params }),

  getOpportunityBoard: (params: BoardParams = {}) =>
    invoke<OpportunityCluster[]>("get_opportunity_board", { params }),

  getClusterHistory: (clusterKey: string) =>
    invoke<ClusterHistoryPoint[]>("get_cluster_history", { clusterKey }),

  getOpportunityDetail: (redditId: string) =>
    invoke<RadarFeedEntry | null>("get_opportunity_detail", { redditId }),

  listSubreddits: () => invoke<SubredditHealth[]>("list_subreddits"),

  listRuns: (limit = 50) => invoke<PipelineRun[]>("list_runs", { limit }),

  // --- Escrituras ---

  updateOpportunityStatus: (
    opportunityId: string,
    status: ValidationStatus,
    notes?: string,
  ) =>
    invoke<void>("update_opportunity_status", {
      opportunityId,
      status,
      notes: notes ?? null,
    }),

  upsertSubreddit: (params: UpsertSubredditParams) =>
    invoke<string>("upsert_subreddit", { params }),

  // --- Motor: Rust las delega en el sidecar Python ---

  searchHybrid: (params: SearchParams) =>
    invoke<HybridSearchHit[]>("search_hybrid", { params }),

  triggerScan: (params: ScanParams) => invoke<string>("trigger_scan", { params }),

  cancelScan: (runId: string) => invoke<void>("cancel_scan", { runId }),
} as const;

/**
 * Se suscribe al progreso de las ejecuciones.
 *
 * El backend empuja los avances en lugar de que la interfaz pregunte: un
 * escaneo puede durar minutos y sondearlo sería ruido constante.
 */
export function onRadarEvent(
  handler: (event: RadarEvent) => void,
): Promise<UnlistenFn> {
  return listen<RadarEvent>(RADAR_EVENT_CHANNEL, (message) =>
    handler(message.payload),
  );
}
