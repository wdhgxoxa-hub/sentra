import { useEffect } from "react";

import { DatabaseStatusScreen } from "@/components/DatabaseStatusScreen";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Sidebar } from "@/components/Sidebar";
import { onRadarEvent, onSourcesEvent } from "@/lib/ipc";
import { queryClient, queryKeys, useDatabaseStatus } from "@/lib/queries";
import { useMultiscanStore } from "@/stores/multiscanStore";
import { useProgressStore } from "@/stores/progressStore";
import { useT } from "@/stores/settingsStore";
import { useUiStore } from "@/stores/uiStore";
import { OpportunityDetail } from "@/views/OpportunityDetail";
import { PipelineControl } from "@/views/PipelineControl";
import { RadarViewPage } from "@/views/RadarView";
import { SearchConsole } from "@/views/SearchConsole";
import { SettingsView } from "@/views/SettingsView";
import { SourcesView } from "@/views/SourcesView";

export default function App() {
  const t = useT();
  const view = useUiStore((state) => state.view);
  const applyProgress = useProgressStore((state) => state.apply);
  const applyMultiscan = useMultiscanStore((state) => state.apply);
  const baseDeDatos = useDatabaseStatus();
  const sinBase = baseDeDatos.data !== undefined && !baseDeDatos.data.connected;

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

  // El escaneo multifuente sigue aunque se cambie de vista: se escucha aquí.
  useEffect(() => {
    const unlisten = onSourcesEvent((evento) => {
      applyMultiscan(evento);
      // Veredictos nuevos: el Top del juez hay que volver a leerlo.
      if (evento.type === "judge:done") {
        void queryClient.invalidateQueries({ queryKey: ["radar", "judge"] });
      }
      // La evidencia se guarda aunque el juez falle o el escaneo se corte.
      if (evento.type === "scan:done" || evento.type === "error") {
        void queryClient.invalidateQueries({ queryKey: ["radar", "evidence"] });
      }
    });
    return () => {
      void unlisten.then((stop) => stop());
    };
  }, [applyMultiscan]);

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
            {/* Sin PostgreSQL no hay vista que pueda leer nada, salvo los
                ajustes, que viven en el motor (D-F). */}
            {sinBase && baseDeDatos.data && view !== "settings" ? (
              <DatabaseStatusScreen status={baseDeDatos.data} />
            ) : (
              <>
                {view === "radar" && <RadarViewPage />}
                {view === "opportunity" && <OpportunityDetail />}
                {view === "search" && <SearchConsole />}
                {view === "pipeline" && <PipelineControl />}
                {view === "settings" && <SettingsView />}
                {view === "sources" && <SourcesView />}
              </>
            )}
          </ErrorBoundary>
        </div>
      </main>
    </div>
  );
}
