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
  type ArchitectChunk,
  ARCHITECT_EVENT_CHANNEL,
  type BlueprintDoc,
  type GeminiModelsResult,
  type GeminiSummary,
  type QuoteTranslation,
  type AppHealth,
  type DatabaseStatus,
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
  type TopOpportunities,
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

  /** [pg] Top N de la ultima ejecucion terminada; null si aun no hay. */
  getTopOpportunities: () =>
    invoke<TopOpportunities | null>("get_top_opportunities"),

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
  generateBlueprint: (clusterKey: string, language: string, architecture: string | null) =>
    invoke<BlueprintDoc>("generate_blueprint", { clusterKey, language, architecture }),

  /**
   * [pg + sidecar] Genera el documento en PDF y lo guarda donde se elija.
   *
   * Devuelve la ruta guardada, o null si se canceló el diálogo. `architecture`
   * es el plan de Gemini de esta sesión, si existe (AUD-008).
   */
  exportPdf: (clusterKey: string, language: string, architecture: string | null) =>
    invoke<string | null>("export_pdf", { clusterKey, language, architecture }),

  /** [sidecar] Traduce citas al idioma de la interfaz. */
  translateQuotes: (texts: string[], target: string) =>
    invoke<QuoteTranslation[]>("translate_quotes", { texts, target }),

  /**
   * [sidecar] Guarda la clave de Gemini y los modelos en el .env del
   * proyecto. Modelo vacío = automático; clave vacía = se conserva la guardada.
   */
  saveGeminiKey: (apiKey: string, model: string, generalModel: string) =>
    invoke<GeminiSummary>("save_gemini_key", { params: { apiKey, model, generalModel } }),

  /** [sidecar] Modelos que la clave guardada puede usar (lista en vivo). */
  listGeminiModels: () => invoke<GeminiModelsResult>("list_gemini_models"),

  /** [sidecar] Comprueba contra Google que la clave sirve. */
  testGeminiKey: () => invoke<ProbeResult>("test_gemini_key"),

  /** [pg + sidecar] Genera el plan de arquitectura. Emite por el canal. */
  generateArchitecture: (clusterKey: string, language: string) =>
    invoke<string>("generate_architecture", { clusterKey, language }),

  /** [pg + sidecar] Estado de las tres piezas por separado. */
  getAppHealth: () => invoke<AppHealth>("get_app_health"),

  /** [pg] Si hay conexión con PostgreSQL y, si no, por qué (D-F). */
  getDatabaseStatus: () => invoke<DatabaseStatus>("get_database_status"),

  /** [pg] Vuelve a intentar la conexión con PostgreSQL. */
  retryDatabase: () => invoke<DatabaseStatus>("retry_database"),
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

/**
 * Escucha el plan de arquitectura mientras se escribe.
 *
 * Se suscribe al montar y no al pulsar: los primeros trozos llegan antes de
 * que un efecto disparado por el clic alcance a registrarse.
 */
export function onArchitectChunk(
  handler: (chunk: ArchitectChunk) => void,
): Promise<UnlistenFn> {
  return listen<ArchitectChunk>(ARCHITECT_EVENT_CHANNEL, (event) =>
    handler(event.payload),
  );
}
