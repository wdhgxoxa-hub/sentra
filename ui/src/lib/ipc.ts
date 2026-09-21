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
 * Todos los declarados aqui existen en Rust: declarar un comando sin
 * backend solo produce fallos en tiempo de ejecucion.
 */

import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

import {
  RADAR_EVENT_CHANNEL,
  type BlueprintDoc,
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
  type SubredditRow,
  type ClusterValidation,
  type CancelResult,
  type UpsertSubredditParams,
  type ValidationStatus,
  type AppSettings,
  type CredentialsInput,
  type CredentialsSummary,
  type FetcherMode,
  type ProbeResult,
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

  /** [pg] Registra el juicio humano sobre un problema recurrente. */
  updateOpportunityStatus: (
    clusterKey: string,
    status: ValidationStatus,
    notes?: string | null,
    assignedTo?: string | null,
  ) =>
    invoke<ClusterValidation>("update_opportunity_status", {
      clusterKey,
      status,
      notes: notes ?? null,
      assignedTo: assignedTo ?? null,
    }),

  /** [pg] Alta o edicion de un subreddit vigilado. */
  upsertSubreddit: (params: UpsertSubredditParams) =>
    invoke<SubredditRow>("upsert_subreddit", { params }),

  /** [sidecar + pg] Interrumpe un escaneo en curso. */
  cancelScan: (runId: string) => invoke<CancelResult>("cancel_scan", { runId }),

  /** [sidecar] Fuente de datos activa y estado de las credenciales. */
  getSettings: () => invoke<AppSettings>("get_settings"),

  /** [sidecar] Alterna entre el corpus de demostracion y Reddit. */
  setFetcherMode: (mode: FetcherMode) =>
    invoke<FetcherMode>("set_fetcher_mode", { mode }),

  /** [sidecar] Guarda las credenciales en el .env del proyecto. */
  saveRedditCredentials: (credentials: CredentialsInput) =>
    invoke<CredentialsSummary>("save_reddit_credentials", { credentials }),

  /** [sidecar] Pide un token real a Reddit con lo guardado. */
  testRedditConnection: () => invoke<ProbeResult>("test_reddit_connection"),

  /** [pg + sidecar] Redacta la especificacion de proyecto de un cluster. */
  generateBlueprint: (clusterKey: string, language: string) =>
    invoke<BlueprintDoc>("generate_blueprint", { clusterKey, language }),

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
