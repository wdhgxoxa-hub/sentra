/**
 * Planes de arquitectura de la sesión
 * ===================================
 *
 * El plan que redacta Gemini vive mientras la ventana está abierta. Se guarda
 * aquí, por oportunidad, para que la exportación a PDF (AUD-008) lo incluya
 * si se generó en esta sesión; si no existe, el documento lo declara «No
 * generado». No se persiste en disco ni en la base (eso es la deuda D32).
 */

import { create } from "zustand";

interface ArchitectState {
  /** Markdown del plan, por clave de oportunidad. */
  plans: Record<string, string>;
  setPlan: (clusterKey: string, markdown: string) => void;
}

export const useArchitectStore = create<ArchitectState>((set) => ({
  plans: {},
  setPlan: (clusterKey, markdown) =>
    set((state) => ({ plans: { ...state.plans, [clusterKey]: markdown } })),
}));

// Igual que los demás stores: tras un intercambio en caliente se recarga la
// ventana para no dejar componentes apuntando a una instancia vieja.
if (import.meta.hot) {
  import.meta.hot.accept(() => window.location.reload());
}
