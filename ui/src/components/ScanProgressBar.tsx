import { AlertCircle, CheckCircle2, Loader2, X } from "lucide-react";

import { PipelineGraph } from "@/components/PipelineGraph";
import { useT } from "@/stores/settingsStore";
import {
  completionRatio,
  useProgressStore,
  type ScanProgress,
} from "@/stores/progressStore";

/**
 * Avance de un escaneo.
 *
 * Muestra la fase y los contadores, no solo un porcentaje: cuando algo
 * tarda, lo que tranquiliza es ver «descargados 25, analizando», no una
 * barra al 40 % sin contexto.
 */
export function ScanProgressBar({
  progress,
  onCancel,
}: {
  progress: ScanProgress;
  onCancel?: () => void;
}) {
  const t = useT();
  const clear = useProgressStore((state) => state.clear);
  const ratio = completionRatio(progress);
  const stats = progress.stats;

  const running = progress.status === "running";
  const failed = progress.status === "error";

  const barColor = failed
    ? "bg-[--color-danger]"
    : running
      ? "bg-[--color-accent]"
      : "bg-[--color-ok]";

  const StatusIcon = failed ? AlertCircle : running ? Loader2 : CheckCircle2;

  return (
    <div className="enter rounded-[--radius-card] border border-[--color-border] bg-[--color-surface] p-3 shadow-[--shadow-card]">
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2">
          <StatusIcon
            className={`size-4 shrink-0 ${
              failed
                ? "text-[--color-danger]"
                : running
                  ? "animate-spin text-[--color-accent]"
                  : "text-[--color-ok]"
            }`}
            aria-hidden="true"
          />
          <span className="truncate font-mono text-sm">r/{progress.subreddit}</span>
          <span className="shrink-0 rounded bg-[--color-surface-2] px-1.5 py-0.5 text-[11px] text-[--color-ink-soft]">
            {t.pipeline.cycle} {progress.cycle}
          </span>
        </span>

        <div className="flex shrink-0 items-center gap-1">
          {running && onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="rounded-md px-2 py-0.5 text-xs text-[--color-ink-soft] transition-colors hover:bg-[--color-surface-2] hover:text-[--color-danger]"
            >
              {t.pipeline.cancel}
            </button>
          )}
          {!running && (
            <button
              type="button"
              onClick={() => clear(progress.runId)}
              aria-label={t.pipeline.discard}
              className="rounded-md p-1 text-[--color-ink-faint] transition-colors hover:bg-[--color-surface-2] hover:text-[--color-ink]"
            >
              <X className="size-3.5" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      <div
        className={`mt-2.5 h-1.5 overflow-hidden rounded-full bg-[--color-surface-2] ${
          running && ratio === 0 ? "sweeping" : ""
        }`}
        role="progressbar"
        aria-valuenow={Math.round(ratio * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${t.pipeline.running}: r/${progress.subreddit}`}
      >
        <div
          className={`h-full rounded-full transition-[width] duration-500 ease-out ${barColor}`}
          style={{ width: `${Math.round(ratio * 100)}%` }}
        />
      </div>

      <div className="mt-2.5">
        <PipelineGraph
          completed={progress.completed}
          current={progress.currentNode}
          compact
        />
      </div>

      <p className="mt-2 font-mono text-[11px] tabular-nums text-[--color-ink-soft]">
        {t.pipeline.read} {stats.fetched ?? 0} · {t.pipeline.analysed}{" "}
        {stats.analyzed ?? 0} · {t.pipeline.stored}{" "}
        {stats.stored ?? 0} · {t.pipeline.clusters} {stats.clusters ?? 0}
        {progress.status === "finished" && progress.clusters !== null && (
          <>
            {" "}
            · {t.pipeline.qualified} {progress.clusters}
          </>
        )}
      </p>

      {progress.message && (
        <p
          className={`mt-1.5 text-xs ${
            failed ? "text-[--color-danger]" : "text-[--color-warn]"
          }`}
        >
          {progress.message}
        </p>
      )}
    </div>
  );
}
