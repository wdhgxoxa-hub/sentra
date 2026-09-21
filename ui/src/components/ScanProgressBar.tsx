import {
  completionRatio,
  useProgressStore,
  type ScanProgress,
} from "@/stores/progressStore";
import { NODE_LABELS, PIPELINE_NODES } from "@/types/radar";

/**
 * Avance de un escaneo, nodo a nodo.
 *
 * Se muestra qué fase va y con qué números, no solo un porcentaje: cuando
 * un escaneo tarda, lo que tranquiliza es ver que descargó 25 posts y está
 * analizando, no una barra al 40 % sin más.
 */
export function ScanProgressBar({ progress }: { progress: ScanProgress }) {
  const clear = useProgressStore((state) => state.clear);
  const ratio = completionRatio(progress);
  const stats = progress.stats;

  const barColor =
    progress.status === "error"
      ? "bg-[--color-urgency-critical]"
      : progress.status === "finished"
        ? "bg-[--color-urgency-low]"
        : "bg-[--color-urgency-high]";

  return (
    <div className="rounded-md border border-[--color-border-subtle] p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">r/{progress.subreddit}</span>
        <div className="flex items-center gap-2 text-xs text-[--color-ink-muted]">
          <span>ciclo {progress.cycle}</span>
          {progress.status !== "running" && (
            <button
              type="button"
              onClick={() => clear(progress.runId)}
              className="rounded px-1.5 py-0.5 hover:bg-[--color-surface-raised]"
            >
              descartar
            </button>
          )}
        </div>
      </div>

      <div
        className="mt-2 h-2 overflow-hidden rounded-full bg-[--color-border-subtle]"
        role="progressbar"
        aria-valuenow={Math.round(ratio * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Progreso del escaneo de r/${progress.subreddit}`}
      >
        <div
          className={`h-2 rounded-full transition-[width] duration-300 ${barColor}`}
          style={{ width: `${Math.round(ratio * 100)}%` }}
        />
      </div>

      <ol className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs">
        {PIPELINE_NODES.map((node) => {
          const done = progress.completed.includes(node);
          const active = progress.currentNode === node;
          return (
            <li
              key={node}
              className={
                active
                  ? "font-semibold"
                  : done
                    ? "text-[--color-ink-muted]"
                    : "text-[--color-ink-muted] opacity-50"
              }
            >
              <span aria-hidden="true">{done ? "✓" : active ? "•" : "·"}</span>{" "}
              {NODE_LABELS[node]}
            </li>
          );
        })}
      </ol>

      <p className="mt-2 font-mono text-xs tabular-nums text-[--color-ink-muted]">
        leídos {stats.fetched ?? 0} · analizados {stats.analyzed ?? 0} · guardados{" "}
        {stats.stored ?? 0} · clusters {stats.clusters ?? 0}
        {progress.status === "finished" && progress.clusters !== null && (
          <> · cualificados {progress.clusters}</>
        )}
      </p>

      {progress.message && (
        <p
          className={
            progress.status === "error"
              ? "mt-1 text-xs text-[--color-urgency-critical]"
              : "mt-1 text-xs text-[--color-urgency-medium]"
          }
        >
          {progress.message}
        </p>
      )}
    </div>
  );
}
