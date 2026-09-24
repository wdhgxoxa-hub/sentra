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
  type GeminiModelsResult,
  type GeminiSummary,
  type AppHealth,
  type DatabaseStatus,
  type HybridSearchHit,
  type SearchParams,
  type CancelResult,
  type AppSettings,
  type ProbeResult,
  SOURCES_EVENT_CHANNEL,
  type MultiScanEvent,
  type ScanProfileInput,
  type SourceCard,
  type EvidenceFeed,
  type SourceProbeResult,
  type SourcesOverview,
  type JudgeTop,
} from "@/types/radar";

export const ipc = {
  /** [sidecar] Busqueda hibrida densa + BM25 con fusion RRF. */
  searchHybrid: (params: SearchParams) =>
    invoke<HybridSearchHit[]>("search_hybrid", { params }),

  /** [sidecar + pg] Interrumpe un escaneo en curso. */
  cancelScan: (runId: string) => invoke<CancelResult>("cancel_scan", { runId }),

  /** [sidecar] Fuente de datos activa y estado de las credenciales. */
  getSettings: () => invoke<AppSettings>("get_settings"),

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

  /** [pg + sidecar] Estado de las tres piezas por separado. */
  getAppHealth: () => invoke<AppHealth>("get_app_health"),

  /** [pg] Si hay conexión con PostgreSQL y, si no, por qué (D-F). */
  getDatabaseStatus: () => invoke<DatabaseStatus>("get_database_status"),

  /** [pg] Vuelve a intentar la conexión con PostgreSQL. */
  retryDatabase: () => invoke<DatabaseStatus>("retry_database"),

  /** [sidecar] Cada fuente con su estado verificado y el modo comercial. */
  listSources: () => invoke<SourcesOverview>("list_sources"),

  /** [sidecar] Guarda credenciales de una fuente. Nunca vuelven. */
  saveSourceCredentials: (source: string, values: Record<string, string>) =>
    invoke<SourceCard>("save_source_credentials", { source, values }),

  /** [sidecar] Llamada mínima real a la API de la fuente. */
  probeSource: (source: string) => invoke<SourceProbeResult>("probe_source", { source }),

  /** [sidecar] Enciende o apaga una fuente. */
  setSourceEnabled: (source: string, enabled: boolean) =>
    invoke<SourceCard>("set_source_enabled", { source, enabled }),

  /** [sidecar] Modo comercial: excluye las de «solo uso personal». */
  setCommercialMode: (enabled: boolean) =>
    invoke<SourcesOverview>("set_commercial_mode", { enabled }),

  /**
   * [sidecar] Escaneo multifuente. El progreso llega por `onSourcesEvent`;
   * la promesa devuelve el último evento (`scan:done` o `error`).
   */
  triggerMultiscan: (profile: ScanProfileInput) =>
    invoke<MultiScanEvent>("trigger_multiscan", { profile }),

  /** [sidecar] Top 6 del juez: de una ejecución o de la última juzgada. */
  getJudgeTop: (runId: string | null = null) => invoke<JudgeTop>("get_judge_top", { runId }),

  /** [sidecar] Evidencia multifuente más reciente, con atribución. */
  getEvidenceFeed: (limit: number | null = null) =>
    invoke<EvidenceFeed>("get_evidence_feed", { limit }),
} as const;


/** Se suscribe al progreso del escaneo multifuente, fuente a fuente. */
export function onSourcesEvent(
  handler: (event: MultiScanEvent) => void,
): Promise<UnlistenFn> {
  return listen<MultiScanEvent>(SOURCES_EVENT_CHANNEL, (message) =>
    handler(message.payload),
  );
}

