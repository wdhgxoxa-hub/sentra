/**
 * Contratos de SENTRA
 * ===================
 *
 * Lo que la interfaz recibe de Rust y del sidecar. Los tests de contrato
 * (tests/test_contracts.py y contract_returns_tests.rs) comparan estas
 * interfaces con lo que se serializa de verdad, a partir de
 * `ui/src-tauri/contract/ts_types.json` (`npm run contracts`).
 *
 * Convención: en Python y en SQL los nombres son snake_case y aquí son
 * camelCase; la conversión la hace quien serializa.
 */

// ---------------------------------------------------------------------
// Búsqueda sobre la evidencia (D-C4)
// ---------------------------------------------------------------------

/**
 * Resultado de la búsqueda sobre la evidencia (D-C4): la pieza con su
 * atribución (sin autor, R9) y en qué puesto la encontró cada rama.
 */
export interface EvidenceSearchHit {
  id: string;
  source: string;
  community: string;
  kind: string;
  title: string | null;
  excerpt: string;
  url: string;
  createdAt: string;
  dataSource: EvidenceDataSource;
  attribution: EvidenceAttribution;
  rrfScore: number;
  /** null = no lo encontró la rama densa (vectores e5). */
  denseRank: number | null;
  /** null = no lo encontró la rama léxica (texto en PostgreSQL). */
  lexicalRank: number | null;
}

export interface SearchParams {
  query: string;
  limit?: number;
}

/** Origen de la evidencia multifuente (CHECK de `evidence_items.data_source`). */
export type EvidenceDataSource = "real" | "demo";

// ---------------------------------------------------------------------
// Salud, configuración y cancelación
// ---------------------------------------------------------------------

export interface ComponentHealth {
  ok: boolean;
  detail: string;
}

/** Por qué no se pudo arrancar el motor (D-D); `code` se traduce. */
export interface LaunchFailure {
  code: string;
  detail: string;
}

/** Resultado de arrancar el motor (`SidecarStatus` de Rust, en camelCase). */
export type SidecarStatus =
  | "alreadyRunning"
  | "started"
  | "unresponsive"
  | "failedToSpawn"
  | "noInterpreter"
  | "portInUse";

/** Canal por el que Rust avisa del arranque del motor (y de cada reintento). */
export const SIDECAR_EVENT_CHANNEL = "sentra:sidecar";

export interface AppHealth {
  /** true solo si las tres piezas responden. */
  ok: boolean;
  version: string;
  app: ComponentHealth;
  postgres: ComponentHealth;
  sidecar: ComponentHealth;
  /** Cuerpo de /api/health del sidecar, si respondio. */
  sidecarInfo: {
    uptimeSeconds: number;
    persistence: { enabled: boolean; target: string | null };
  } | null;
  /** Por qué no arrancó el motor; null si arrancó o ya estaba. */
  sidecarLaunch: LaunchFailure | null;
}

export interface CancelResult {
  runId: string;
  /** El sidecar tenía ese escaneo en marcha. */
  wasActive: boolean;
  /** Se marcó la ejecución como cancelada en PostgreSQL. */
  markedInDatabase: boolean;
}

/** Configuración: dónde está el `.env` y el estado de Gemini (D-C5). */
export interface AppSettings {
  envPath: string;
  gemini: GeminiSummary;
}

export interface ProbeResult {
  ok: boolean;
  detail: string;
  /** Código del fallo; `gemini_key_rejected` es el único que dice que la clave es mala (D1). */
  code: string | null;
}

// ---------------------------------------------------------------------
// Fuentes y escaneo multifuente
// ---------------------------------------------------------------------

/** Verde solo con una respuesta real de la API (core/sources/registry.py). */
export type SourceStatusName =
  | "no_configurada"
  | "configurada_sin_verificar"
  | "verificada"
  | "error"
  | "deshabilitada_por_usuario";

/** En qué se mide el gasto de una fuente. */
export type SourceCostUnit = "request" | "quota_unit" | "usd";

/** Qué credencial hay, nunca su valor. */
export interface SourceCredentialState {
  name: string;
  envVar: string;
  secret: boolean;
  required: boolean;
  configured: boolean;
}

export interface SourceCard {
  source: string;
  displayName: string;
  /** Términos de la plataforma, enlazados desde la tarjeta. */
  termsUrl: string;
  /** false = «solo uso personal»: el modo comercial la excluye. */
  commercialUseAllowed: boolean;
  requiresCredentials: boolean;
  credentialFields: SourceCredentialState[];
  status: SourceStatusName;
  /** Última respuesta real con éxito (ISO 8601). */
  lastVerifiedAt: string | null;
  /** Código estable del último fallo (source_*), solo en `error`. */
  errorCode: string | null;
  detail: string | null;
  disabled: boolean;
  excludedByCommercialMode: boolean;
  /** Entra en el escaneo (misma regla que el sidecar, no se recalcula aquí). */
  active: boolean;
  costUnit: SourceCostUnit;
  costNote: string;
}

export interface SourcesOverview {
  commercialMode: boolean;
  sources: SourceCard[];
}

/**
 * Atribución obligatoria de cada pieza de evidencia (R5; términos de Stack
 * Exchange): insignia de la plataforma, sitio y URL del original en texto
 * plano. La calcula el motor (core/sources/attribution.py).
 */
export interface EvidenceAttribution {
  badge: string;
  site: string;
  url: string;
}

/** Resultado del botón «Probar». `checkedAt` null = no llegó a llamar. */
export interface SourceProbeResult {
  ok: boolean;
  code: string | null;
  detail: string;
  checkedAt: string | null;
}

/** Perfil de escaneo (core/sources/profile.py). Sin tema = descubrimiento. */
export interface ScanProfileInput {
  name: string;
  keywords: string[];
  discovery: boolean;
  windowDays: number;
  languages: string[];
}

export interface SourceScanSummary {
  status: "running" | "done" | "failed";
  items: number;
  errorCode: string | null;
  detail: string | null;
  /** Presupuesto agotado: termina sin fallar. */
  stopReason: string | null;
  requests: number;
  units: number;
  usd: number;
}

export type MultiScanEvent =
  | {
      type: "scan:started";
      /** Id para cancelar con `cancelScan`: el de la ejecución si se guarda. */
      scanId: string;
      runId: string | null;
      sources: string[];
    }
  | { type: "source:started"; source: string }
  | { type: "source:progress"; source: string; items: number }
  | { type: "source:done"; source: string; items: number; stopReason: string | null }
  | { type: "source:error"; source: string; items: number; code: string; detail: string | null }
  | {
      type: "scan:done";
      runId: string | null;
      /** Lo pidió quien miraba; lo traído hasta entonces se guarda igual. */
      cancelled: boolean;
      persisted: boolean;
      persistError: string | null;
      /** Todo lo traído, duplicados incluidos. */
      fetched: number;
      canonical: number;
      duplicates: number;
      perSource: Record<string, SourceScanSummary>;
    }
  | { type: "judge:started"; runId: string }
  | { type: "judge:done"; runId: string; summary: JudgeSummary }
  | { type: "judge:error"; runId: string; code: string; message: string }
  | { type: "error"; code: string; message: string };

/** Resumen del juez tras un escaneo guardado (core/judge/pipeline.py). */
export interface JudgeSummary {
  items: number;
  kept: number;
  /** Descartes del filtro de calidad, por motivo. */
  discarded: Record<string, number>;
  /** Autopromoción conservada como señal de competencia. */
  competition: number;
  labeled: number;
  /** Ítems sin etiqueta del LLM, por motivo (no_provider, llm_budget_exhausted...). */
  undetermined: Record<string, number>;
  clusters: number;
  verdicts: Record<string, number>;
  llm: { model: string | null; unavailable: string | null; calls: number };
}

export const SOURCES_EVENT_CHANNEL = "sources:events";

// ---------------------------------------------------------------------
// Juez de nichos y evidencia reciente
// ---------------------------------------------------------------------

export type NicheVerdict = "CONSTRUIR" | "INVESTIGAR MÁS" | "DESCARTAR";

/** Una compuerta G1–G8: pasa o no, valor medido frente a umbral y su evidencia. */
export interface JudgeGate {
  gate: string;
  passed: boolean;
  value: number;
  threshold: number;
  evidenceIds: string[];
}

/** Una de las siete dimensiones; `normalized` null = undetermined (viabilidad en F3). */
export interface JudgeDimension {
  name: string;
  value: number | null;
  normalized: number | null;
  itemIds: string[];
  /** «sin_datos» o «undetermined» cuando la cifra no sale de evidencia. */
  note: string | null;
}

export interface AdvocateArgumentView {
  claim: string;
  evidenceIds: string[];
  severity: "bloqueante" | "importante" | "menor";
}

/** Abogado del diablo: solo puede bajar el veredicto. */
export interface JudgeAdvocate {
  verdictBefore: NicheVerdict;
  verdictAfter: NicheVerdict;
  downgraded: boolean;
  reason: string | null;
  arguments: AdvocateArgumentView[];
  /** Argumentos que citaban evidencia ajena al grupo: no cuentan. */
  discarded: AdvocateArgumentView[];
}

/** Evidencia que se enseña, siempre con su atribución (R5, D-SE3). */
export interface JudgeEvidence {
  id: string;
  source: string;
  excerpt: string;
  createdAt: string;
  attribution: EvidenceAttribution;
}

export interface JudgeVerdict {
  id: string;
  opportunityId: string | null;
  clusterKey: string;
  keywords: string[];
  verdict: NicheVerdict;
  /** Regla de la tabla D-M3 que decidió. */
  rule: string;
  score: number;
  weightsVersion: string;
  /** Etiquetador (versión/modelo); null = desconocido (veredicto anterior a la 011). */
  labelerVersion: string | null;
  clusteringVersion: string;
  /** Compuertas que fallan. */
  missing: string[];
  memberCount: number;
  memberIds: string[];
  gates: JudgeGate[];
  dimensions: JudgeDimension[];
  advocate: JudgeAdvocate;
  /** Mapa de corroboración: menciones por fuente. */
  corroboration: Record<string, number>;
  evidence: JudgeEvidence[];
}

/** Versiones con las que juzga el código actual: lo distinto es antiguo (B4). */
export interface JudgeVersions {
  labeler: string;
  clustering: string;
  weights: string;
}

/**
 * Top 6 (AUD-007): CONSTRUIR primero; sin rellenar si no hay 6. `rest` es el
 * resto de veredictos de la misma ejecución en el mismo orden (C1).
 */
export interface JudgeTop {
  runId: string | null;
  target: number;
  buildCount: number;
  reason: string | null;
  verdicts: JudgeVerdict[];
  rest: JudgeVerdict[];
  currentVersions: JudgeVersions;
}

/** Una pieza de evidencia multifuente del feed del Radar; sin autor (R9). */
export interface EvidenceFeedEntry {
  id: string;
  source: string;
  community: string;
  kind: string;
  title: string | null;
  excerpt: string;
  url: string;
  createdAt: string;
  dataSource: EvidenceDataSource;
  attribution: EvidenceAttribution;
}

export interface EvidenceFeed {
  items: EvidenceFeedEntry[];
}

// ---------------------------------------------------------------------
// Gemini y base de datos
// ---------------------------------------------------------------------

/** Un modelo que la clave puede usar (lista en vivo, `models.list`). */
export interface GeminiModel {
  id: string;
  displayName: string;
}

/**
 * Modelos que la clave puede usar y el que se usaría en cada uso. Con
 * `ok = false`, `code` dice por qué (sin clave, clave mala, sin red).
 */
export interface GeminiModelsResult {
  ok: boolean;
  code: string | null;
  detail: string;
  models: GeminiModel[];
  /** Modelo general que se usaría ahora (el guardado o el automático). */
  general: string | null;
  /** Modelo de documentos que se usaría ahora. */
  documents: string | null;
}

/** Estado del motor de arquitectura. La clave entera no sale del sidecar. */
export interface GeminiSummary {
  configured: boolean;
  keyMasked: string;
  /** Modelo de documentos guardado; `null` = automático (el Pro 3.x más reciente). */
  model: string | null;
  /** Modelo general guardado; `null` = automático (el Flash 3.x estable más reciente). */
  generalModel: string | null;
}

/** Conexión con PostgreSQL (D-F): sin ella la app arranca y lo dice. */
export interface DatabaseStatus {
  connected: boolean;
  /** Código traducible del fallo; null si hay conexión. */
  code: string | null;
  /** Detalle técnico, para «Detalles técnicos». */
  detail: string | null;
}
