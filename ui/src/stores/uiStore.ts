/**
 * Estado de interfaz (Zustand)
 * ============================
 *
 * Aquí vive solo lo que no tiene dueño en el servidor: qué vista está
 * abierta y qué se está buscando. Los datos viven en TanStack Query.
 */

import { create } from "zustand";

export type RadarView = "radar" | "search" | "sources" | "settings";

interface UiState {
  view: RadarView;
  setView: (view: RadarView) => void;

  // --- Consola de búsqueda ---
  searchQuery: string;
  setSearchQuery: (query: string) => void;
}

export const useUiStore = create<UiState>((set) => ({
  view: "radar",
  setView: (view) => set({ view }),

  searchQuery: "",
  setSearchQuery: (searchQuery) => set({ searchQuery }),
}));

// El estado global no sobrevive a un intercambio en caliente: los componentes
// ya montados siguen apuntando a la instancia anterior y la vista se queda en
// blanco. Recargar la ventana es barato y siempre deja un estado coherente.
if (import.meta.hot) {
  import.meta.hot.accept(() => window.location.reload());
}
