/**
 * Estado de interfaz (Zustand)
 * ============================
 *
 * Aquí vive solo lo que no tiene dueño en el servidor: qué vista está
 * abierta, qué filtros hay puestos, qué oportunidad está seleccionada. Los
 * datos viven en TanStack Query.
 *
 * La separación importa: si los filtros vivieran junto a los datos, cambiar
 * un filtro invalidaría la caché en lugar de cambiar la clave de consulta.
 */

import { create } from "zustand";

import type { UrgencyTier } from "@/types/radar";

export type RadarView = "radar" | "opportunity" | "search" | "pipeline";

interface UiState {
  view: RadarView;
  setView: (view: RadarView) => void;

  /** Señal seleccionada en el feed (su id de Reddit). */
  selectedRedditId: string | null;
  selectRedditId: (redditId: string | null) => void;

  /** Oportunidad agregada seleccionada (su clave natural). */
  selectedClusterKey: string | null;
  selectClusterKey: (clusterKey: string | null) => void;

  // --- Filtros del Radar View ---
  urgencyFilter: UrgencyTier[];
  toggleUrgency: (tier: UrgencyTier) => void;
  minScore: number;
  setMinScore: (value: number) => void;
  subredditFilter: string | null;
  setSubredditFilter: (name: string | null) => void;
  /** true = solo oportunidades que superan el corte y no arrastran riesgos. */
  qualifiedOnly: boolean;
  toggleQualifiedOnly: () => void;
  resetFilters: () => void;

  // --- Consola de búsqueda ---
  searchQuery: string;
  setSearchQuery: (query: string) => void;
}

const DEFAULT_FILTERS = {
  urgencyFilter: [] as UrgencyTier[],
  minScore: 0,
  subredditFilter: null as string | null,
  qualifiedOnly: false,
};

export const useUiStore = create<UiState>((set) => ({
  view: "radar",
  setView: (view) => set({ view }),

  selectedRedditId: null,
  selectRedditId: (selectedRedditId) => set({ selectedRedditId }),

  selectedClusterKey: null,
  selectClusterKey: (selectedClusterKey) => set({ selectedClusterKey }),

  ...DEFAULT_FILTERS,

  toggleUrgency: (tier) =>
    set((state) => ({
      urgencyFilter: state.urgencyFilter.includes(tier)
        ? state.urgencyFilter.filter((t) => t !== tier)
        : [...state.urgencyFilter, tier],
    })),

  setMinScore: (minScore) => set({ minScore }),
  setSubredditFilter: (subredditFilter) => set({ subredditFilter }),
  toggleQualifiedOnly: () =>
    set((state) => ({ qualifiedOnly: !state.qualifiedOnly })),
  resetFilters: () => set({ ...DEFAULT_FILTERS }),

  searchQuery: "",
  setSearchQuery: (searchQuery) => set({ searchQuery }),
}));
