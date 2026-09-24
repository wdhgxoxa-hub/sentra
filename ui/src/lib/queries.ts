/**
 * Cliente de datos (TanStack Query)
 * =================================
 *
 * Veredictos, evidencia y fuentes son *caché del servidor*, no
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
  SearchParams,
  JudgeTop,
  EvidenceFeed,
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
  evidenceFeed: (limit: number) => ["radar", "evidence", limit] as const,
} as const;

// --- Lecturas ---------------------------------------------------------

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

/** Reintenta arrancar el motor; al volver, la salud se lee de nuevo. */
export function useRetrySidecar() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => ipc.retrySidecar(),
    onSettled: () => client.invalidateQueries({ queryKey: queryKeys.health }),
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

/**
 * Cancela un escaneo en curso.
 *
 * No invalida nada al terminar: el escaneo cortado emite su `scan:done` por
 * el canal, que ya dispara el refresco (App.tsx).
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

export function useEvidenceFeed(limit: number) {
  return useQuery<EvidenceFeed>({
    queryKey: queryKeys.evidenceFeed(limit),
    queryFn: () => ipc.getEvidenceFeed(limit),
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
