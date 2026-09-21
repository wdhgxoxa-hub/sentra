import { useEffect } from "react";

import { onRadarEvent } from "@/lib/ipc";
import { queryClient, queryKeys } from "@/lib/queries";
import { useUiStore, type RadarView } from "@/stores/uiStore";
import { OpportunityDetail } from "@/views/OpportunityDetail";
import { PipelineControl } from "@/views/PipelineControl";
import { RadarViewPage } from "@/views/RadarView";
import { SearchConsole } from "@/views/SearchConsole";

const TABS: Array<{ id: RadarView; label: string }> = [
  { id: "radar", label: "Radar" },
  { id: "opportunity", label: "Oportunidad" },
  { id: "search", label: "Búsqueda" },
  { id: "pipeline", label: "Pipeline" },
];

export default function App() {
  const view = useUiStore((state) => state.view);
  const setView = useUiStore((state) => state.setView);

  // Cuando termina un escaneo, se invalida la caché en lugar de sondear.
  useEffect(() => {
    const unlisten = onRadarEvent((event) => {
      if (event.type === "run:finished" || event.type === "run:error") {
        queryClient.invalidateQueries({ queryKey: queryKeys.radar });
      }
    });
    return () => {
      void unlisten.then((stop) => stop());
    };
  }, []);

  return (
    <div className="flex h-full flex-col">
      <header className="drag-region flex items-center gap-1 border-b border-[--color-border-subtle] px-4 py-2">
        <h1 className="mr-4 text-sm font-semibold tracking-tight">
          Reddit Intelligence Radar
        </h1>
        <nav className="flex gap-1" aria-label="Vistas principales">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setView(tab.id)}
              aria-current={view === tab.id ? "page" : undefined}
              className={
                view === tab.id
                  ? "rounded-md bg-[--color-surface-raised] px-3 py-1 text-sm font-medium"
                  : "rounded-md px-3 py-1 text-sm text-[--color-ink-muted] hover:bg-[--color-surface-raised]"
              }
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </header>

      <main className="min-h-0 flex-1 overflow-auto p-4">
        {view === "radar" && <RadarViewPage />}
        {view === "opportunity" && <OpportunityDetail />}
        {view === "search" && <SearchConsole />}
        {view === "pipeline" && <PipelineControl />}
      </main>
    </div>
  );
}
