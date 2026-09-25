import { Suspense, lazy, useEffect } from "react";

import { DatabaseStatusScreen } from "@/components/DatabaseStatusScreen";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Sidebar } from "@/components/Sidebar";
import { onSidecarEvent, onSourcesEvent } from "@/lib/ipc";
import { queryClient, queryKeys, useDatabaseStatus } from "@/lib/queries";
import { useMultiscanStore } from "@/stores/multiscanStore";
import { useT } from "@/stores/settingsStore";
import { useUiStore } from "@/stores/uiStore";
import { NuevoEscaneo } from "@/pantallas/NuevoEscaneo";

// «Nuevo escaneo» es lo primero que se ve (Fase 2) y va en el chunk
// principal; las demás vistas se cargan al abrirlas (C3: dividir en lugar
// de subir el límite).
const RadarViewPage = lazy(() =>
  import("@/views/RadarView").then((m) => ({ default: m.RadarViewPage })),
);
const SearchConsole = lazy(() =>
  import("@/views/SearchConsole").then((m) => ({ default: m.SearchConsole })),
);
const SettingsView = lazy(() =>
  import("@/views/SettingsView").then((m) => ({ default: m.SettingsView })),
);
const SourcesView = lazy(() =>
  import("@/views/SourcesView").then((m) => ({ default: m.SourcesView })),
);

export default function App() {
  const t = useT();
  const view = useUiStore((state) => state.view);
  const applyMultiscan = useMultiscanStore((state) => state.apply);
  const baseDeDatos = useDatabaseStatus();
  const sinBase = baseDeDatos.data !== undefined && !baseDeDatos.data.connected;

  // AUD-059: el arranque del motor avisa al terminar (y al reintentarlo);
  // sin escucharlo, la salud seguía en rojo hasta el siguiente sondeo de 30 s.
  useEffect(() => {
    // Todo lo que depende del motor cuelga de ["radar"]: al cambiar su estado
    // se refresca entero. Una lista a mano dejó fuera el juez y la evidencia,
    // y el Radar se quedaba vacío si cargaba antes de que el motor arrancase.
    const unlisten = onSidecarEvent(() => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.radar });
    });
    return () => {
      void unlisten.then((stop) => stop());
    };
  }, []);

  // El escaneo multifuente sigue aunque se cambie de vista: se escucha aquí;
  // al terminar se invalida la caché en lugar de sondear.
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
      {/* La barra lateral lleva su propio límite: fuera de él, un fallo de
          render del indicador de salud dejaba la ventana entera en negro. */}
      <ErrorBoundary textos={t.error} resetKey={view}>
        <Sidebar />
      </ErrorBoundary>

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
              <Suspense fallback={<p className="text-sm text-ink-faint">{t.common.loading}</p>}>
                {view === "nuevo" && <NuevoEscaneo />}
                {view === "radar" && <RadarViewPage />}
                {view === "search" && <SearchConsole />}
                {view === "settings" && <SettingsView />}
                {view === "sources" && <SourcesView />}
              </Suspense>
            )}
          </ErrorBoundary>
        </div>
      </main>
    </div>
  );
}
