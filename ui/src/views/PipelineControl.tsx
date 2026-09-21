import { ScanProgressBar } from "@/components/ScanProgressBar";
import { SubredditForm } from "@/components/SubredditForm";
import {
  useCancelScan,
  useRuns,
  useSubreddits,
  useTriggerScan,
  useUpsertSubreddit,
} from "@/lib/queries";
import { useProgressStore } from "@/stores/progressStore";

/** Centro de control: disparar escaneos y leer la telemetria del grafo. */
export function PipelineControl() {
  const subreddits = useSubreddits();
  const runs = useRuns(20);
  const scan = useTriggerScan();
  const activos = useProgressStore((state) => Object.values(state.runs));
  const limpiar = useProgressStore((state) => state.clearFinished);
  const cancelar = useCancelScan();
  const guardar = useUpsertSubreddit();

  return (
    <div className="flex flex-col gap-6">
      {activos.length > 0 && (
        <section aria-labelledby="progreso">
          <div className="mb-2 flex items-center justify-between">
            <h2 id="progreso" className="text-base font-semibold">
              Escaneos en curso
            </h2>
            <button
              type="button"
              onClick={limpiar}
              className="text-xs text-[--color-ink-muted] hover:underline"
            >
              limpiar terminados
            </button>
          </div>
          <div className="flex flex-col gap-2">
            {activos.map((progreso) => (
              <div key={progreso.runId} className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <ScanProgressBar progress={progreso} />
                </div>
                {progreso.status === "running" && (
                  <button
                    type="button"
                    disabled={cancelar.isPending}
                    onClick={() => cancelar.mutate(progreso.runId)}
                    className="rounded-md border border-[--color-border-subtle] px-3 py-1 text-sm hover:bg-[--color-surface-raised] disabled:opacity-50"
                  >
                    Cancelar
                  </button>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="mb-2 text-base font-semibold">Subreddits vigilados</h2>
        <div className="mb-3">
          <SubredditForm />
        </div>
        <ul className="flex flex-col gap-2">
          {subreddits.data?.map((item) => (
            <li
              key={item.subredditId}
              className="flex items-center justify-between rounded-md border border-[--color-border-subtle] px-3 py-2"
            >
              <div>
                <p className="text-sm font-medium">r/{item.name}</p>
                <p className="text-xs text-[--color-ink-muted]">
                  {item.status}, ultima ejecucion: {item.lastRunStatus ?? "nunca"}
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={guardar.isPending}
                  onClick={() =>
                    guardar.mutate({
                      name: item.name,
                      status: item.status === "active" ? "paused" : "active",
                    })
                  }
                  className="rounded-md border border-[--color-border-subtle] px-3 py-1 text-sm disabled:opacity-50"
                >
                  {item.status === "active" ? "Pausar" : "Activar"}
                </button>
                <button
                  type="button"
                  disabled={scan.isPending || item.status !== "active"}
                  onClick={() =>
                    scan.mutate({
                      subreddit: item.name,
                      limit: 25,
                      sort: item.listing,
                    })
                  }
                  className="rounded-md bg-[--color-surface-raised] px-3 py-1 text-sm disabled:opacity-50"
                >
                  Escanear
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="mb-2 text-base font-semibold">Ejecuciones recientes</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-[--color-ink-muted]">
            <tr>
              <th scope="col" className="py-1">
                Subreddit
              </th>
              <th scope="col" className="py-1">
                Estado
              </th>
              <th scope="col" className="py-1">
                Leidos
              </th>
              <th scope="col" className="py-1">
                Cualificados
              </th>
              <th scope="col" className="py-1">
                Errores
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[--color-border-subtle]">
            {runs.data?.map((run) => (
              <tr key={run.id}>
                <td className="py-2">r/{run.subredditName}</td>
                <td className="py-2">{run.status}</td>
                <td className="py-2 font-mono tabular-nums">{run.fetched}</td>
                <td className="py-2 font-mono tabular-nums">{run.qualified}</td>
                <td className="py-2 font-mono tabular-nums">{run.errorCount}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
