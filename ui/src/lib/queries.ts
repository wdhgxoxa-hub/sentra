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
  BoardParams,
  FeedParams,
  ScanParams,
  SearchParams,
  UpsertSubredditParams,
  ValidationStatus,
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
  search: (params: SearchParams) => ["radar", "search", params] as const,
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

export function useOpportunityDetail(redditId: string | null) {
  return useQuery({
    queryKey: queryKeys.opportunity(redditId ?? ""),
    queryFn: () => ipc.getOpportunityDetail(redditId as string),
    enabled: Boolean(redditId),
  });
}

export function useSubreddits() {
  return useQuery({
    queryKey: queryKeys.subreddits,
    queryFn: () => ipc.listSubreddits(),
  });
}

export function useRuns(limit = 50) {
  return useQuery({
    queryKey: queryKeys.runs(limit),
    queryFn: () => ipc.listRuns(limit),
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

export function useUpdateOpportunityStatus() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      opportunityId,
      status,
      notes,
    }: {
      opportunityId: string;
      status: ValidationStatus;
      notes?: string;
    }) => ipc.updateOpportunityStatus(opportunityId, status, notes),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.radar }),
  });
}

export function useUpsertSubreddit() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (params: UpsertSubredditParams) => ipc.upsertSubreddit(params),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.subreddits }),
  });
}
