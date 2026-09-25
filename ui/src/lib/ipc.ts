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
  type GeminiBudget,
  type GeminiModelsResult,
  type GeminiSummary,
  type AppHealth,
  type DatabaseStatus,
  type EvidenceSearchHit,
  type SearchParams,
  type CancelResult,
  type AppSettings,
  type ProbeResult,
  SOURCES_EVENT_CHANNEL,
  type MultiScanEvent,
  type ScanEstimate,
  type ScanProfileInput,
  type SourceCard,
  type SidecarStatus,
  SIDECAR_EVENT_CHANNEL,
  type EvidenceFeed,
  type SourceProbeResult,
  type SourcesOverview,
  type JudgeTop,
  type ExportDocumentParams,
  type ExportedDocument,
} from "@/types/radar";

export const ipc = {
  /** [sidecar + pg] Busqueda sobre la evidencia: e5 + texto, fusion RRF. */
  searchHybrid: (params: SearchParams) =>
    invoke<EvidenceSearchHit[]>("search_hybrid", { params }),

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

  /** [sidecar] Topes de Gemini (llm_budget_settings) y lo gastado hoy. */
  getGeminiBudget: () => invoke<GeminiBudget>("get_gemini_budget"),

  /** [sidecar] Guarda los cuatro topes de Gemini en la base. */
  saveGeminiBudget: (params: Omit<GeminiBudget, "spentToday">) =>
    invoke<GeminiBudget>("save_gemini_budget", { params }),

  /** [pg + sidecar] Estado de las tres piezas por separado. */
  getAppHealth: () => invoke<AppHealth>("get_app_health"),

  /** [pg] Si hay conexión con PostgreSQL y, si no, por qué (D-F). */
  getDatabaseStatus: () => invoke<DatabaseStatus>("get_database_status"),

  /** [sidecar] Vuelve a arrancar el motor si no responde (AUD-056). */
  retrySidecar: () => invoke<SidecarStatus>("retry_sidecar"),

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
  triggerMultiscan: (profile: ScanProfileInput, confirmation: string) =>
    invoke<MultiScanEvent>("trigger_multiscan", { profile, confirmation }),

  /**
   * [sidecar] Estimación del gasto de Gemini del escaneo y el identificador
   * que el escaneo exige (un solo uso, caduca): sin confirmarla no se escanea.
   */
  estimateScan: (profile: ScanProfileInput) => invoke<ScanEstimate>("estimate_scan", { profile }),

  /** [sidecar] Top 6 del juez: de una ejecución o de la última juzgada. */
  getJudgeTop: (runId: string | null = null) => invoke<JudgeTop>("get_judge_top", { runId }),

  /**
   * [sidecar] Dossier o plan de un veredicto en PDF o Markdown, guardado con
   * el diálogo nativo. `null` si se canceló el diálogo.
   */
  exportDocument: (params: ExportDocumentParams) =>
    invoke<ExportedDocument | null>("export_document", { params }),

  /** [sidecar] Evidencia multifuente más reciente, con atribución. */
  getEvidenceFeed: (limit: number | null = null) =>
    invoke<EvidenceFeed>("get_evidence_feed", { limit }),
} as const;


/** Se suscribe al estado del arranque del motor (AUD-059). */
export function onSidecarEvent(
  handler: (status: SidecarStatus) => void,
): Promise<UnlistenFn> {
  return listen<SidecarStatus>(SIDECAR_EVENT_CHANNEL, (message) => handler(message.payload));
}

/** Se suscribe al progreso del escaneo multifuente, fuente a fuente. */
export function onSourcesEvent(
  handler: (event: MultiScanEvent) => void,
): Promise<UnlistenFn> {
  return listen<MultiScanEvent>(SOURCES_EVENT_CHANNEL, (message) =>
    handler(message.payload),
  );
}

