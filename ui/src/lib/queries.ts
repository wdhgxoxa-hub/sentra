/**
 * Cliente de datos (TanStack Query)
 * =================================
 *
 * El feed, las oportunidades y la telemetría son *caché del servidor*, no
 * estado de la aplicación: tienen dueño en PostgreSQL y aquí solo se
 * replican. Por eso viven en TanStack Query y no en el store de Zustand,
 * que guarda únicamente lo que es de la interfaz.
 */

import {
  QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { ipc } from "@/lib/ipc";
import type {
  AppSettings,
  GeminiModelsResult,
  BlueprintDoc,
  BoardParams,
  CredentialsInput,
  FetcherMode,
  FeedParams,
  ScanParams,
  SearchParams,
  UpsertSubredditParams,
  ValidationStatus,
  JudgeTop,
  ScanProfileInput,
  SourcesOverview,
} from "@/types/radar";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Los datos vienen de un escaneo que ocurre cada muchos minutos:
      // refrescar al enfocar la ventana solo gastaría consultas.
      refetchOnWindowFocus: false,
      staleTime: 30_000,
      retry: 1,
    },
  },
});

/** Claves jerárquicas: invalidar `["radar"]` alcanza a todo lo derivado. */
export const queryKeys = {
  radar: ["radar"] as const,
  feed: (params: FeedParams) => ["radar", "feed", params] as const,
  board: (params: BoardParams) => ["radar", "board", params] as const,
  clusterHistory: (key: string) => ["radar", "cluster", key] as const,
  opportunity: (redditId: string) => ["radar", "opportunity", redditId] as const,
  subreddits: ["radar", "subreddits"] as const,
  runs: (limit: number) => ["radar", "runs", limit] as const,
  top: ["radar", "top"] as const,
  health: ["radar", "health"] as const,
  // Fuera de ["radar"] a propósito: invalidar los datos no debe volver a
  // preguntar por la conexión, que solo cambia al reintentar.
  database: ["database"] as const,
  settings: ["radar", "settings"] as const,
  // Bajo `settings`: guardar la clave la invalida con el resto de ajustes.
  geminiModels: ["radar", "settings", "gemini-models"] as const,
  search: (params: SearchParams) => ["radar", "search", params] as const,
  sources: ["radar", "sources"] as const,
  judgeTop: (runId: string | null) => ["radar", "judge", runId] as const,
  blueprint: (key: string, language: string, architecture: string | null) =>
    ["radar", "blueprint", key, language, architecture] as const,
} as const;

// --- Lecturas ---------------------------------------------------------

export function useRadarFeed(params: FeedParams = {}) {
  return useQuery({
    queryKey: queryKeys.feed(params),
    queryFn: () => ipc.getRadarFeed(params),
  });
}

export function useOpportunityBoard(params: BoardParams = {}) {
  return useQuery({
    queryKey: queryKeys.board(params),
    queryFn: () => ipc.getOpportunityBoard(params),
  });
}

export function useClusterHistory(clusterKey: string | null) {
  return useQuery({
    queryKey: queryKeys.clusterHistory(clusterKey ?? ""),
    queryFn: () => ipc.getClusterHistory(clusterKey as string),
    enabled: Boolean(clusterKey),
  });
}

export function useOpportunityDetail(clusterKey: string | null) {
  return useQuery({
    queryKey: queryKeys.opportunity(clusterKey ?? ""),
    queryFn: () => ipc.getOpportunityDetail(clusterKey as string),
    enabled: Boolean(clusterKey),
  });
}

export function useSubreddits() {
  return useQuery({
    queryKey: queryKeys.subreddits,
    queryFn: () => ipc.getSubreddits(),
  });
}

export function useRuns(limit = 50) {
  return useQuery({
    queryKey: queryKeys.runs(limit),
    queryFn: () => ipc.getPipelineRuns(limit),
  });
}

/**
 * Top N de la última ejecución terminada (AUD-007).
 *
 * Cuelga del árbol `radar`, así que se refresca solo cuando un escaneo
 * termina (App.tsx invalida `["radar"]` con `run:finished` y `run:error`).
 */
export function useTopOpportunities() {
  return useQuery({
    queryKey: queryKeys.top,
    queryFn: () => ipc.getTopOpportunities(),
  });
}

/**
 * Salud de las tres piezas.
 *
 * Se refresca sola cada 30 s: que el sidecar se haya caido es justo lo que
 * hay que saber sin tener que recargar la ventana.
 */
/** Conexión con PostgreSQL (D-F). */
export function useDatabaseStatus() {
  return useQuery({
    queryKey: queryKeys.database,
    queryFn: () => ipc.getDatabaseStatus(),
    staleTime: Infinity,
  });
}

/** Reintenta la conexión; si vuelve, todo lo leído antes queda viejo. */
export function useRetryDatabase() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => ipc.retryDatabase(),
    onSuccess: (status) => {
      client.setQueryData(queryKeys.database, status);
      if (status.connected) void client.invalidateQueries({ queryKey: queryKeys.radar });
    },
  });
}

export function useAppHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => ipc.getAppHealth(),
    refetchInterval: 30_000,
    staleTime: 0,
  });
}

/**
 * Búsqueda híbrida.
 *
 * Solo se lanza con una consulta no vacía: un `useQuery` sin `enabled`
 * dispararía una búsqueda al montar el componente.
 */
export function useHybridSearch(params: SearchParams) {
  return useQuery({
    queryKey: queryKeys.search(params),
    queryFn: () => ipc.searchHybrid(params),
    enabled: params.query.trim().length > 0,
  });
}

// --- Escrituras -------------------------------------------------------

export function useTriggerScan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (params: ScanParams) => ipc.triggerScan(params),
    // El escaneo es asíncrono: lo que llega aquí es el id de la ejecución,
    // no su resultado. El refresco de verdad lo dispara `run:finished`.
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.subreddits }),
  });
}

/**
 * Registra el juicio humano sobre una oportunidad.
 *
 * Invalida todo el arbol `radar`: el estado de validacion viaja dentro de
 * `v_opportunity_board`, asi que el tablero, la ficha y el feed lo muestran.
 */
export function useUpdateOpportunityStatus() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      clusterKey,
      status,
      notes,
      assignedTo,
    }: {
      clusterKey: string;
      status: ValidationStatus;
      notes?: string | null;
      assignedTo?: string | null;
    }) => ipc.updateOpportunityStatus(clusterKey, status, notes, assignedTo),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.radar }),
  });
}

export function useUpsertSubreddit() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (params: UpsertSubredditParams) => ipc.upsertSubreddit(params),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: queryKeys.subreddits }),
  });
}

/**
 * Cancela un escaneo en curso.
 *
 * No invalida nada al terminar: el evento `run:cancelled` que llega por el
 * canal ya dispara el refresco, y hacerlo aqui duplicaria las consultas.
 */
export function useCancelScan() {
  return useMutation({
    mutationFn: (runId: string) => ipc.cancelScan(runId),
  });
}

// --- Configuracion ----------------------------------------------------

export function useSettings() {
  return useQuery<AppSettings>({
    queryKey: queryKeys.settings,
    queryFn: () => ipc.getSettings(),
    // Si el motor no responde, reintentar cada pocos segundos llenaria el
    // log de errores sin aportar nada: el indicador de salud ya lo dice.
    retry: false,
  });
}

export function useSetFetcherMode() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (mode: FetcherMode) => ipc.setFetcherMode(mode),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.settings }),
  });
}

export function useSaveCredentials() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (credentials: CredentialsInput) =>
      ipc.saveRedditCredentials(credentials),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.settings }),
  });
}

/**
 * Prueba la conexion con Reddit.
 *
 * Es una mutacion y no una consulta porque tiene efecto: pide un token real
 * y consume cuota. No debe dispararse sola al montar la vista.
 */
export function useTestConnection() {
  return useMutation({
    mutationFn: () => ipc.testRedditConnection(),
  });
}

// --- Fuentes (F2) -----------------------------------------------------

export function useSources() {
  return useQuery<SourcesOverview>({
    queryKey: queryKeys.sources,
    queryFn: () => ipc.listSources(),
    // Igual que los ajustes: si el motor no responde, lo dice la salud.
    retry: false,
  });
}

export function useSaveSourceCredentials() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ source, values }: { source: string; values: Record<string, string> }) =>
      ipc.saveSourceCredentials(source, values),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.sources }),
  });
}

/** Mutación y no consulta: hace una llamada real y gasta cuota. */
export function useProbeSource() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (source: string) => ipc.probeSource(source),
    onSettled: () => client.invalidateQueries({ queryKey: queryKeys.sources }),
  });
}

export function useSetSourceEnabled() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ source, enabled }: { source: string; enabled: boolean }) =>
      ipc.setSourceEnabled(source, enabled),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.sources }),
  });
}

export function useSetCommercialMode() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) => ipc.setCommercialMode(enabled),
    onSuccess: (overview) => client.setQueryData(queryKeys.sources, overview),
  });
}

export function useJudgeTop(runId: string | null = null) {
  return useQuery<JudgeTop>({
    queryKey: queryKeys.judgeTop(runId),
    queryFn: () => ipc.getJudgeTop(runId),
    retry: false,
  });
}

/** Al terminar, el estado de cada fuente cambió (verificada o en error). */
export function useTriggerMultiscan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (profile: ScanProfileInput) => ipc.triggerMultiscan(profile),
    onSettled: () => client.invalidateQueries({ queryKey: queryKeys.sources }),
  });
}

/**
 * Especificacion de proyecto de un cluster.
 *
 * No se pide al abrir la ficha: se redacta cuando alguien lo pulsa. El
 * documento depende del idioma, que forma parte de la clave, asi que cambiar
 * de idioma lo vuelve a pedir en lugar de servir el anterior.
 */
/**
 * Documento de la oportunidad (D-H). `architecture` es el plan de Gemini de
 * la sesión: la sección 7 lo incluye, igual que el PDF.
 */
export function useBlueprint(
  clusterKey: string | null,
  language: string,
  enabled: boolean,
  architecture: string | null,
) {
  return useQuery<BlueprintDoc>({
    queryKey: queryKeys.blueprint(clusterKey ?? "", language, architecture),
    queryFn: () => ipc.generateBlueprint(clusterKey as string, language, architecture),
    enabled: enabled && Boolean(clusterKey),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
}

// --- Motor de arquitectura -------------------------------------------

/**
 * Guarda la clave de Gemini.
 *
 * Al terminar invalida la configuracion para que la insignia de «configurada»
 * y el modelo activo se refresquen sin recargar la ventana.
 */
export function useSaveGeminiKey() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      apiKey,
      model,
      generalModel,
    }: {
      apiKey: string;
      model: string;
      generalModel: string;
    }) => ipc.saveGeminiKey(apiKey, model, generalModel),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.settings }),
  });
}

/**
 * Modelos que la clave guardada puede usar. Solo se pregunta con clave: sin
 * ella no hay lista que pedir. El sidecar la reutiliza unos minutos.
 */
export function useGeminiModels(enabled: boolean) {
  return useQuery<GeminiModelsResult>({
    queryKey: queryKeys.geminiModels,
    queryFn: () => ipc.listGeminiModels(),
    enabled,
    retry: false,
  });
}

/** Prueba la clave contra Google. Es mutacion: gasta cuota. */
export function useTestGeminiKey() {
  return useMutation({
    mutationFn: () => ipc.testGeminiKey(),
  });
}
