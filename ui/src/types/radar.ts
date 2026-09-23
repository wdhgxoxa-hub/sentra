/**
 * Contratos de SENTRA
 * =======================================
 *
 * Espejo de los tipos del esquema PostgreSQL y de los modelos Pydantic del
 * motor. Las uniones literales replican exactamente los ENUM de
 * `sql/migrations/001_initial_schema.sql`: si alguien añade un valor allí y
 * no aquí, TypeScript deja de cubrir ese caso.
 *
 * Convención: las columnas SQL son snake_case y aquí son camelCase. La
 * conversión la hace la capa Rust al serializar, de modo que el frontend
 * nunca ve nombres de base de datos.
 */

// ---------------------------------------------------------------------
// ENUM del esquema (migración 001)
// ---------------------------------------------------------------------

export type UrgencyTier = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export type BuyingIntent =
  | "ready_to_buy"
  | "seeking_recommendation"
  | "seeking_alternative"
  | "comparing_products"
  | "casual_discussion"
  | "undetermined"
  | "none";

export type PainSeverity =
  | "severe_blocker"
  | "time_consuming_friction"
  | "minor_inconvenience"
  | "no_problem"
  | "undetermined"
  | "none";

export type SentimentLabel =
  | "negative_frustration"
  | "neutral_inquiry"
  | "positive_praise"
  | "undetermined"
  | "unknown";

export type WillingnessToPay = "explicit" | "implicit" | "none";

export type UrgencyLevel = "critical" | "high" | "medium" | "low";

export type SubredditStatus = "active" | "paused" | "error" | "archived";

export type ListingSort = "hot" | "new" | "top" | "rising";

export type RunStatus = "running" | "completed" | "failed" | "cancelled";

export type ValidationStatus =
  | "new"
  | "triaged"
  | "validated"
  | "rejected"
  | "shipped";

export type TriggerSource = "manual" | "schedule" | "mcp" | "api";

// ---------------------------------------------------------------------
// Umbrales (core/orchestration/state.py)
// ---------------------------------------------------------------------

/** Corte de higiene sobre la señal individual: ¿entra al feed? */
export const SIGNAL_THRESHOLD = 20.0;

/** Corte de oportunidad sobre el problema agregado: ¿merece producto? */
export const OPPORTUNITY_CLUSTER_THRESHOLD = 60.0;

// ---------------------------------------------------------------------
// Scoring
// ---------------------------------------------------------------------

/**
 * Los cinco factores del scoring temporal, cada uno en 0..1, con sus pesos.
 *
 * Se transporta entero y no solo el total porque un 73.5 no dice nada: lo
 * que informa es "difusión 1.0, frecuencia 0.24", que significa que el
 * problema está extendido pero todavía no es recurrente.
 */
export interface ScoreBreakdown {
  spreadFactor: number;
  frequencyFactor: number;
  severityFactor: number;
  recencyFactor: number;
  paidSignalFactor: number;
  rawScore: number;
  finalScore: number;
}

/** Pesos de la fórmula, para pintar el desglose sin recalcularlos. */
export const SCORE_WEIGHTS = {
  spreadFactor: 0.25,
  frequencyFactor: 0.25,
  severityFactor: 0.2,
  recencyFactor: 0.15,
  paidSignalFactor: 0.15,
} as const satisfies Record<keyof Omit<ScoreBreakdown, "rawScore" | "finalScore">, number>;

// ---------------------------------------------------------------------
// Señales individuales (vista v_radar_feed)
// ---------------------------------------------------------------------

export interface RadarFeedEntry {
  signalId: string;
  redditId: string;
  subredditName: string;
  author: string;
  content: string;
  /** ISO 8601 con zona. */
  createdUtc: string;
  finalScore: number;
  urgencyTier: UrgencyTier;
  buyingIntent: BuyingIntent;
  painSeverity: PainSeverity;
  sentiment: SentimentLabel;
  riskFlags: string[];
  qualified: boolean;
  jobStatement: string | null;
  postTitle: string | null;
  postPermalink: string | null;
  /** Fuente del registro (D-J); null = desconocida. */
  dataSource: DataSource | null;
}

// ---------------------------------------------------------------------
// Oportunidades agregadas (vista v_opportunity_board, migración 002)
// ---------------------------------------------------------------------

/** Una cita literal que sostiene una oportunidad. */
export interface EvidenceQuote {
  signalId: string;
  subreddit: string;
  author: string;
  quote: string;
  url: string | null;
  score: number;
  /** Fecha de la queja (epoch UTC); null en lecturas anteriores a AUD-008. */
  createdUtc: number | null;
}

/**
 * Un problema recurrente consolidado.
 *
 * Es el objeto sobre el que se decide construir producto, y no debe
 * confundirse con `RadarFeedEntry`, que es una queja suelta.
 */
export interface OpportunityCluster {
  id: string;
  /** Clave natural estable: permite seguir el problema entre ejecuciones. */
  clusterKey: string;
  label: string;
  intentType: string;
  keywords: string[];
  subreddits: string[];

  mentionCount: number;
  communityCount: number;
  linkedSignals: number;

  jobStatement: string;
  currentSolutions: string[];
  riskFlags: string[];

  breakdown: ScoreBreakdown;
  urgencyTier: UrgencyTier;
  qualified: boolean;

  evidence: EvidenceQuote[];
  representativeRedditId: string | null;
  representativeContent: string | null;

  runId: string | null;
  runStartedAt: string | null;
  createdAt: string;

  /** Estado del juicio humano. 'new' si nadie lo ha mirado todavía. */
  validationStatus: ValidationStatus;
  validationNotes: string | null;
  validationAssignee: string | null;
  validatedAt: string | null;

  /** Cifras exactas sobre todas las quejas del problema (AUD-009). */
  clusterStats: ClusterStats;
  /** Fuente de la ejecución que produjo esta lectura. */
  dataSource: DataSource | null;
  /** Identidad estable entre escaneos (D-G): la clave cambia, esto no. */
  opportunityId: string;
}

/**
 * Cifras de `aggregation.cluster_stats`; vacío en lecturas anteriores.
 *
 * Rust lo reenvía como JSON tal cual sale de PostgreSQL, así que las claves
 * conservan el snake_case de Python.
 */
export interface ClusterStats {
  mentions?: number;
  distinct_texts?: number;
  severity_undetermined?: number;
  /** Quejas clasificadas por cada motor: `heuristic` o `transformers`. */
  classifier_engines?: Record<string, number>;
  keywords?: Array<{ keyword: string; count: number }>;
  pairs?: Array<{ a: string; b: string; count: number }>;
}

/** Una lectura histórica de un cluster, para la curva de evolución. */
export interface ClusterHistoryPoint {
  id: string;
  runId: string | null;
  finalScore: number;
  urgencyTier: UrgencyTier;
  mentionCount: number;
  communityCount: number;
  qualified: boolean;
  createdAt: string;
  /** Fuente del registro (D-J); null = desconocida. */
  dataSource: DataSource | null;
}

// ---------------------------------------------------------------------
// Búsqueda híbrida (LanceDB + BM25 con fusión RRF)
// ---------------------------------------------------------------------

export interface HybridSearchHit {
  id: string;
  text: string;
  subreddit: string;
  opportunityScore: number;
  urgencyTier: UrgencyTier;
  jobStatement: string;
  currentSolution: string | null;
  rrfScore: number;
  /** null = no lo encontró la rama densa. */
  denseRank: number | null;
  /** null = no lo encontró la rama léxica. */
  bm25Rank: number | null;
  bm25Score: number | null;
  /** Fuente del registro (D-J); null = desconocida. */
  dataSource: DataSource | null;
}

// ---------------------------------------------------------------------
// Configuración y telemetría
// ---------------------------------------------------------------------

export interface SubredditHealth {
  subredditId: string;
  name: string;
  status: SubredditStatus;
  listing: ListingSort;
  lastScannedAt: string | null;
  nextScanAt: string | null;
  consecutiveFailures: number;
  lastRunId: string | null;
  lastRunStatus: RunStatus | null;
  lastRunStartedAt: string | null;
  lastRunDurationMs: number | null;
  fetched: number | null;
  qualified: number | null;
  errorCount: number | null;
  /** Fuente de la última ejecución (D-J); null = desconocida. */
  lastRunDataSource: DataSource | null;
}

export interface PipelineRun {
  id: string;
  subredditName: string;
  status: RunStatus;
  triggerSource: TriggerSource;
  startedAt: string;
  finishedAt: string | null;
  durationMs: number | null;
  cycles: number;
  fetched: number;
  filteredIn: number;
  filteredOut: number;
  analyzed: number;
  stored: number;
  qualified: number;
  rejected: number;
  errors: string[];
  errorCount: number;
  /** Fuente del registro (D-J); null = desconocida. */
  dataSource: DataSource | null;
}

// ---------------------------------------------------------------------
// Parámetros de los comandos IPC
// ---------------------------------------------------------------------

export interface FeedParams {
  limit?: number;
  minScore?: number;
  urgencyTiers?: UrgencyTier[];
  subreddit?: string;
}

export interface BoardParams {
  limit?: number;
  minScore?: number;
  qualifiedOnly?: boolean;
  urgencyTiers?: UrgencyTier[];
}

export interface SearchParams {
  query: string;
  minScore?: number;
  limit?: number;
}

export interface ScanParams {
  subreddit: string;
  limit?: number;
  sort?: ListingSort;
}

// ---------------------------------------------------------------------
// Eventos que Rust emite al WebView
// ---------------------------------------------------------------------

export interface RunStats {
  fetched?: number;
  filtered_in?: number;
  filtered_out?: number;
  analyzed?: number;
  stored?: number;
  qualified?: number;
  rejected?: number;
  clusters?: number;
  qualified_clusters?: number;
}

/** Nodos del grafo, en el orden en que se ejecutan. */
export const PIPELINE_NODES = [
  "fetch",
  "filter",
  "comments",
  "intelligence",
  "storage",
  "quality_gate",
  "aggregate",
] as const;

export type PipelineNode = (typeof PIPELINE_NODES)[number];

export const NODE_LABELS: Record<PipelineNode, string> = {
  fetch: "Descarga",
  filter: "Filtrado",
  comments: "Comentarios",
  intelligence: "Análisis",
  storage: "Persistencia",
  quality_gate: "Corte de calidad",
  aggregate: "Agregación",
};

/** Campos del cierre de un escaneo, terminado o cancelado. */
export interface RunClosedFields {
  runId: string;
  persistedRunId: string | null;
  persistError: string | null;
  qualified: number;
  clusters: number;
  stats: RunStats;
  errors: string[];
  dataSource: DataSource;
  top: RunTopOutcome | null;
}

/**
 * Progreso de un escaneo, empujado por Rust.
 *
 * `runId` identifica el escaneo desde que abre el flujo; `persistedRunId`
 * solo existe al final, porque hasta entonces no hay fila en PostgreSQL.
 */
export type RadarEvent =
  | { type: "run:started"; runId: string; subreddit: string }
  | {
      type: "run:progress";
      runId: string;
      node: PipelineNode;
      cycle: number;
      stats: RunStats;
    }
  | ({ type: "run:finished" } & RunClosedFields)
  /**
   * Trae lo mismo que `run:finished`: lo cosechado hasta la cancelación se
   * guarda marcado como tal. No es un error (AUD-010).
   */
  | ({ type: "run:cancelled" } & RunClosedFields)
  | {
      type: "run:error";
      runId: string;
      /** Código estable (core/ingestion/errors.py); la interfaz lo traduce. */
      code: ScanErrorCode;
      /** Detalle técnico para el registro. No se muestra al usuario. */
      message: string;
      retryAfterSeconds: number | null;
      persistedRunId: string | null;
      persistError: string | null;
    };

// ---------------------------------------------------------------------
// Top N de cada ejecución (AUD-007)
// ---------------------------------------------------------------------

/** De dónde salen los datos de una ejecución. */
export type DataSource = "demo" | "reddit";

/** Por qué una ejecución no llegó a su objetivo (ENUM `top_n_reason`). */
export type TopReason =
  | "fuentes_agotadas"
  | "limite_ciclos"
  | "sin_acceso_reddit"
  | "datos_insuficientes";

/** Resultado que emite el motor al terminar (`top_n.run_outcome`). */
export interface RunTopOutcome {
  target: number;
  found: number;
  complete: boolean;
  reason: TopReason | null;
}

/** Una oportunidad del Top N, con la posición que le dio el motor. */
export interface TopItem {
  position: number;
  clusterKey: string;
  label: string;
  finalScore: number;
  mentionCount: number;
  communityCount: number;
}

/** Top N de la última ejecución terminada (comando `get_top_opportunities`). */
export interface TopOpportunities {
  runId: string;
  status: RunStatus;
  dataSource: DataSource | null;
  target: number;
  found: number;
  complete: boolean;
  reason: TopReason | null;
  finishedAt: string | null;
  items: TopItem[];
}

/**
 * Motivos por los que un escaneo falla (AUD-003). Espejo de los `code` de
 * `core/ingestion/errors.py`, más `fetch_failed` (fuente no Reddit) e
 * `internal_error` (fallo del propio motor).
 */
export type ScanErrorCode =
  | "reddit_credentials_missing"
  | "reddit_user_agent_invalid"
  | "reddit_auth_failed"
  | "reddit_forbidden"
  | "reddit_not_found"
  | "reddit_rate_limited"
  | "reddit_unavailable"
  | "fetch_failed"
  | "internal_error";

export const RADAR_EVENT_CHANNEL = "radar:events";

// ---------------------------------------------------------------------
// Resultado de un escaneo (respuesta del sidecar)
// ---------------------------------------------------------------------

export interface ScanResult {
  subreddit: string;
  /** null si el escaneo no se persistio en PostgreSQL. */
  runId: string | null;
  cycles: number;
  stats: Record<string, number>;
  /** Errores no fatales de nodos concretos: la cosecha degrada, no aborta. */
  errors: string[];
  qualified: Array<Record<string, unknown>>;
  clusters: Array<Record<string, unknown>>;
  qualifiedClusters: Array<Record<string, unknown>>;
  persisted: boolean;
}

// ---------------------------------------------------------------------
// Salud de las tres piezas
// ---------------------------------------------------------------------

export interface ComponentHealth {
  ok: boolean;
  detail: string;
}

/**
 * El radar son tres procesos que fallan por separado. Un unico "ok/ko"
 * ocultaria justo lo que hace falta para arreglarlo.
 */
/**
 * Capacidad real de leer datos (AUD-004). Solo `reddit_verificado` significa
 * que Reddit respondió 200 de verdad.
 */
export type SourceState =
  | "demo"
  | "reddit_sin_credenciales"
  | "reddit_sin_verificar"
  | "reddit_verificado"
  | "reddit_error";

export interface SourceStatus {
  state: SourceState;
  /** Último acceso real con éxito (ISO 8601). */
  lastSuccessAt: string | null;
  /** Código del último fallo, en `reddit_error`. */
  errorCode: ScanErrorCode | null;
}

/** Por qué no se pudo arrancar el motor (D-D); `code` se traduce. */
export interface LaunchFailure {
  code: string;
  detail: string;
}

export interface AppHealth {
  /** true solo si las tres piezas responden. */
  ok: boolean;
  version: string;
  app: ComponentHealth;
  postgres: ComponentHealth;
  sidecar: ComponentHealth;
  /** Cuerpo de /api/health del sidecar, si respondio. */
  sidecarInfo: {
    embedder: { name: string; semantic: boolean; dim: number };
    nli: { engine: string; available: boolean; loaded: boolean };
    store: { path: string; records: number };
    uptimeSeconds: number;
  } | null;
  /** Estado real de la fuente; null si el motor no respondió. */
  source: SourceStatus | null;
  /** Por qué no arrancó el motor; null si arrancó o ya estaba. */
  sidecarLaunch: LaunchFailure | null;
}

// ---------------------------------------------------------------------
// Escrituras
// ---------------------------------------------------------------------

/**
 * Juicio humano sobre un problema recurrente.
 *
 * Va por `clusterKey` y no por el id de una lectura: `opportunity_clusters`
 * guarda una fila por ejecución, y validar una fila sería validar una foto.
 */
export interface ClusterValidation {
  clusterKey: string;
  status: ValidationStatus;
  notes: string | null;
  assignedTo: string | null;
  validatedAt: string | null;
  /** Puntuación que tenía el problema cuando se tomó la decisión. */
  scoreAtDecision: number | null;
  updatedAt: string;
}

export interface UpsertSubredditParams {
  name: string;
  listing?: ListingSort;
  limitPerPage?: number;
  minOpportunityScore?: number;
  scanIntervalMinutes?: number;
  status?: SubredditStatus;
  tags?: string[];
}

export interface SubredditRow {
  subredditId: string;
  name: string;
  listing: ListingSort;
  status: SubredditStatus;
  limitPerPage: number;
  minOpportunityScore: number;
  scanIntervalMinutes: number;
  tags: string[];
}

export interface CancelResult {
  runId: string;
  /** El sidecar tenía ese escaneo en marcha. */
  wasActive: boolean;
  /** Se marcó la ejecución como cancelada en PostgreSQL. */
  markedInDatabase: boolean;
}

/** Transiciones ofrecidas en la ficha, en el orden natural del flujo. */
export const VALIDATION_FLOW: ValidationStatus[] = [
  "new",
  "triaged",
  "validated",
  "rejected",
  "shipped",
];

// ---------------------------------------------------------------------
// Configuración
// ---------------------------------------------------------------------

export type FetcherMode = "synthetic" | "reddit";

/**
 * Estado de las credenciales.
 *
 * Nunca incluye el secreto: un secreto que viaja al frontend acaba en el
 * inspector del navegador o en una captura de pantalla.
 */
export interface CredentialsSummary {
  configured: boolean;
  clientIdMasked: string;
  userAgent: string;
  hasUser: boolean;
}

export interface AppSettings {
  fetcherMode: FetcherMode;
  credentials: CredentialsSummary;
  envPath: string;
  syntheticPosts: number;
  gemini: GeminiSummary;
}

export interface CredentialsInput {
  clientId: string;
  clientSecret: string;
  userAgent: string;
  username?: string;
  password?: string;
}

export interface ProbeResult {
  ok: boolean;
  detail: string;
}

// ---------------------------------------------------------------------
// Fuentes (F2): estado verificado, credenciales y escaneo multifuente
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
// Juez de nichos (F3): Top 6 por veredicto
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

/** Top 6 (AUD-007): CONSTRUIR primero; sin rellenar si no hay 6. */
/** Versiones con las que juzga el código actual: lo distinto es antiguo (B4). */
export interface JudgeVersions {
  labeler: string;
  clustering: string;
  weights: string;
}

export interface JudgeTop {
  runId: string | null;
  target: number;
  buildCount: number;
  reason: string | null;
  verdicts: JudgeVerdict[];
  currentVersions: JudgeVersions;
}

// ---------------------------------------------------------------------
// Ayudas de presentación
// ---------------------------------------------------------------------

/**
 * Etiquetas legibles de los ENUM.
 *
 * Están aquí y no repartidas por los componentes para que añadir un valor
 * al esquema obligue a decidir cómo se muestra en un solo sitio.
 */
export const URGENCY_LABELS: Record<UrgencyTier, string> = {
  CRITICAL: "Crítica",
  HIGH: "Alta",
  MEDIUM: "Media",
  LOW: "Baja",
};

export const INTENT_LABELS: Record<BuyingIntent, string> = {
  ready_to_buy: "Listo para comprar",
  seeking_recommendation: "Busca recomendación",
  seeking_alternative: "Busca alternativa",
  comparing_products: "Comparando productos",
  casual_discussion: "Conversación casual",
  undetermined: "Indeterminada",
  none: "Sin intención",
};

export const PAIN_LABELS: Record<PainSeverity, string> = {
  severe_blocker: "Bloqueante grave",
  time_consuming_friction: "Fricción costosa",
  minor_inconvenience: "Molestia menor",
  no_problem: "Sin problema",
  undetermined: "Indeterminada",
  none: "Sin clasificar",
};

export const VALIDATION_LABELS: Record<ValidationStatus, string> = {
  new: "Nueva",
  triaged: "Triada",
  validated: "Validada",
  rejected: "Descartada",
  shipped: "Construida",
};

/** Una oportunidad con riesgos no se cualifica, por alta que sea su puntuación. */
export const BLOCKING_RISK_FLAGS = [
  "affiliate_or_referral_pattern",
  "affiliate_or_promo_spam",
  "astroturfing",
] as const;

export function hasBlockingRisk(riskFlags: readonly string[]): boolean {
  return riskFlags.some((flag) =>
    (BLOCKING_RISK_FLAGS as readonly string[]).includes(flag),
  );
}

/** Una fase del alcance propuesto en la especificacion. */
export interface BlueprintPhase {
  name: string;
  items: string[];
}

/** Una cita textual que sostiene el documento. */
export interface BlueprintQuote {
  quote: string;
  subreddit: string;
  author: string;
  url: string;
}

/**
 * Especificacion de proyecto redactada por el motor.
 *
 * Se regenera a partir de la evidencia cada vez que se pide, asi que no puede
 * quedar desfasada respecto al cluster que describe.
 */
export interface BlueprintDoc {
  productName: string;
  oneLiner: string;
  executiveSummary: string;
  problem: string;
  solution: string;
  mvp: BlueprintPhase[];
  whyExistingFail: string;
  monetisation: string;
  evidence: BlueprintQuote[];
  /** Citas distintas: no es lo mismo que el numero de menciones. */
  distinctQuotes: number;
  markdown: string;
  /** Fuente de los datos, en una frase: va arriba del documento (AUD-009). */
  sourceNotice: string;
  dataSource: DataSource | null;
  /** Las diez secciones del documento, las mismas y en el mismo orden que el PDF (D-H). */
  sections: DocumentSection[];
}

/** Una de las diez secciones del `DocumentModel` (core/documents/model.py). */
export interface DocumentSection {
  id: string;
  title: string;
  blocks: DocumentBlock[];
}

/** Un bloque de contenido; cada tipo usa sus campos y deja el resto vacío. */
export interface DocumentBlock {
  kind: "paragraph" | "note" | "subheading" | "bullets" | "quote" | "table" | "markdown";
  text: string;
  items: string[];
  signature: string;
  rows: string[][];
}

/** Canal por el que llega el plan de arquitectura mientras se escribe. */
export const ARCHITECT_EVENT_CHANNEL = "sentra:architect";

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

/** Un trozo del documento segun se genera. */
export interface ArchitectChunk {
  clusterKey: string;
  text: string;
  /** Solo `true` cuando el motor confirma el plan completo (AUD-020). */
  done: boolean;
  /** Por qué el plan no se dio por terminado; null mientras va bien. */
  error: ArchitectFailure | null;
}

/** Conexión con PostgreSQL (D-F): sin ella la app arranca y lo dice. */
export interface DatabaseStatus {
  connected: boolean;
  /** Código traducible del fallo; null si hay conexión. */
  code: string | null;
  /** Detalle técnico, para «Detalles técnicos». */
  detail: string | null;
}

/** Fallo tipado del plan: `code` se traduce, `detail` es técnico. */
export interface ArchitectFailure {
  code: string;
  detail: string;
  /** Secciones exigidas que no llegaron (solo con `gemini_incomplete`). */
  missing: string[];
}

/**
 * Una cita traducida.
 *
 * `approximate` marca lo que el motor sin conexion solo pudo traducir en
 * parte: leerlo como una traduccion buena cambiaria la lectura de la queja.
 */
export interface QuoteTranslation {
  text: string;
  engine: "gemini" | "offline";
  approximate: boolean;
}
