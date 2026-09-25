/**
 * Estado de interfaz (Zustand)
 * ============================
 *
 * Aquí vive solo lo que no tiene dueño en el servidor: qué vista está
 * abierta y qué se está buscando. Los datos viven en TanStack Query.
 */

import { create } from "zustand";

import type { TipoDeNicho } from "@/modos/tipos";

/** «nuevo» es la pantalla principal (Fase 2): Nuevo escaneo. */
export type RadarView = "nuevo" | "radar" | "search" | "sources" | "settings";

interface UiState {
  view: RadarView;
  setView: (view: RadarView) => void;

  /** Modo activo (P2). Hoy solo hay Software; Videos se enchufará aquí. */
  modo: TipoDeNicho;

  /** Nicho abierto en su ficha (Radar); null = la lista. */
  nichoAbierto: string | null;
  abrirNicho: (id: string | null) => void;

  // --- Consola de búsqueda ---
  searchQuery: string;
  setSearchQuery: (query: string) => void;
}

export const useUiStore = create<UiState>((set) => ({
  view: "nuevo",
  setView: (view) => set({ view }),

  modo: "software",

  nichoAbierto: null,
  abrirNicho: (nichoAbierto) => set({ view: "radar", nichoAbierto }),

  searchQuery: "",
  setSearchQuery: (searchQuery) => set({ searchQuery }),
}));

// El estado global no sobrevive a un intercambio en caliente: los componentes
// ya montados siguen apuntando a la instancia anterior y la vista se queda en
// blanco. Recargar la ventana es barato y siempre deja un estado coherente.
if (import.meta.hot) {
  import.meta.hot.accept(() => window.location.reload());
}
