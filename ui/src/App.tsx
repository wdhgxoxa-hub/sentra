import { useEffect } from "react";

import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Sidebar } from "@/components/Sidebar";
import { onRadarEvent } from "@/lib/ipc";
import { queryClient, queryKeys } from "@/lib/queries";
import { useProgressStore } from "@/stores/progressStore";
import { useT } from "@/stores/settingsStore";
import { useUiStore } from "@/stores/uiStore";
import { OpportunityDetail } from "@/views/OpportunityDetail";
import { PipelineControl } from "@/views/PipelineControl";
import { RadarViewPage } from "@/views/RadarView";
import { SearchConsole } from "@/views/SearchConsole";
import { SettingsView } from "@/views/SettingsView";

export default function App() {
  const t = useT();
  const view = useUiStore((state) => state.view);
  const applyProgress = useProgressStore((state) => state.apply);

  // Un único suscriptor para todo el progreso: alimenta el store y, cuando
  // el escaneo termina, invalida la caché en lugar de sondear.
  useEffect(() => {
    const unlisten = onRadarEvent((event) => {
      applyProgress(event);
      // Un escaneo cancelado también deja datos: lo cosechado hasta ese
      // momento se guarda, así que la caché queda igual de vieja (AUD-010).
      if (
        event.type === "run:finished" ||
        event.type === "run:cancelled" ||
        event.type === "run:error"
      ) {
        queryClient.invalidateQueries({ queryKey: queryKeys.radar });
      }
    });
    return () => {
      void unlisten.then((stop) => stop());
    };
  }, [applyProgress]);

  return (
    <div className="flex h-full bg-bg">
      <Sidebar />

      <main className="min-w-0 flex-1 overflow-auto">
        {/* Franja superior fina: da sitio para arrastrar la ventana y sitúa
            en qué sección se está sin repetir el título de cada vista. */}
        <div className="drag-region sticky top-0 z-10 border-b border-border bg-bg/80 px-6 py-2.5 backdrop-blur">
          <p className="text-xs text-ink-faint">{t.app.tagline}</p>
        </div>

        <div className="p-6">
          {/* Cada vista va envuelta por separado: si una revienta, la barra
              lateral sigue respondiendo y basta con cambiar de sección, que
              además rearma el limite. */}
          <ErrorBoundary textos={t.error} resetKey={view}>
            {view === "radar" && <RadarViewPage />}
            {view === "opportunity" && <OpportunityDetail />}
            {view === "search" && <SearchConsole />}
            {view === "pipeline" && <PipelineControl />}
            {view === "settings" && <SettingsView />}
          </ErrorBoundary>
        </div>
      </main>
    </div>
  );
}
