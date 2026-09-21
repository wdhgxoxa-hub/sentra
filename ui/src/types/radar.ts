/**
 * Contratos del Reddit Intelligence Radar
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
  | "none";

export type PainSeverity =
  | "severe_blocker"
  | "time_consuming_friction"
  | "minor_inconvenience"
  | "no_problem"
  | "none";

export type SentimentLabel =
  | "negative_frustration"
  | "neutral_inquiry"
  | "positive_praise"
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
  /** Identificador del registro en LanceDB. */
  embeddingRef: string | null;

  opportunityId: string | null;
  jobStatement: string | null;
  currentSolution: string | null;
  competitorsMentioned: string[];
  workaroundDetected: boolean;
  willingnessToPay: WillingnessToPay | null;
  validationStatus: ValidationStatus | null;

  postTitle: string | null;
  postPermalink: string | null;
  postScore: number | null;
  numComments: number | null;
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
}

// ---------------------------------------------------------------------
// Búsqueda híbrida (LanceDB + BM25 con fusión RRF)
// ---------------------------------------------------------------------

export interface HybridSearchHit {
  id: string;
  text: string;
  subreddit: string;
  author: string;
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
  "intelligence",
  "storage",
  "quality_gate",
  "aggregate",
] as const;

export type PipelineNode = (typeof PIPELINE_NODES)[number];

export const NODE_LABELS: Record<PipelineNode, string> = {
  fetch: "Descarga",
  filter: "Filtrado",
  intelligence: "Análisis",
  storage: "Persistencia",
  quality_gate: "Corte de calidad",
  aggregate: "Agregación",
};

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
  | {
      type: "run:finished";
      runId: string;
      persistedRunId: string | null;
      persistError: string | null;
      qualified: number;
      clusters: number;
      stats: RunStats;
      errors: string[];
    }
  | { type: "run:error"; runId: string; message: string };

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
  none: "Sin intención",
};

export const PAIN_LABELS: Record<PainSeverity, string> = {
  severe_blocker: "Bloqueante grave",
  time_consuming_friction: "Fricción costosa",
  minor_inconvenience: "Molestia menor",
  no_problem: "Sin problema",
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
}
