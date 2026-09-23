import { AlertCircle, Ban, CheckCircle2, Loader2, X } from "lucide-react";

import { ErrorNotice } from "@/components/ErrorNotice";
import { PipelineGraph } from "@/components/PipelineGraph";
import type { Dictionary } from "@/i18n/es";
import { useT } from "@/stores/settingsStore";
import type { ScanErrorCode } from "@/types/radar";
import {
  completionRatio,
  useProgressStore,
  type ScanProgress,
} from "@/stores/progressStore";

/** Texto del fallo, traducido a partir de su código estable. */
function scanErrorText(
  t: Dictionary,
  code: ScanErrorCode | null,
  retryAfterSeconds: number | null,
): string {
  if (code === "reddit_rate_limited") {
    return retryAfterSeconds === null
      ? t.scanErrors.reddit_rate_limited_unknown
      : t.scanErrors.reddit_rate_limited.replace(
          "{seconds}",
          String(retryAfterSeconds),
        );
  }
  return t.scanErrors[code ?? "internal_error"];
}

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
  const cancelled = progress.status === "cancelled";

  const barColor = failed
    ? "bg-danger"
    : cancelled
      ? "bg-ink-faint"
      : running
        ? "bg-accent"
        : "bg-ok";

  const StatusIcon = failed
    ? AlertCircle
    : cancelled
      ? Ban
      : running
        ? Loader2
        : CheckCircle2;

  return (
    <div className="enter rounded-card border border-border bg-surface p-3 shadow-[var(--shadow-card)]">
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2">
          <StatusIcon
            className={`size-4 shrink-0 ${
              failed
                ? "text-danger"
                : cancelled
                  ? "text-ink-faint"
                  : running
                    ? "animate-spin text-accent"
                    : "text-ok"
            }`}
            aria-hidden="true"
          />
          <span className="truncate font-mono text-sm">r/{progress.subreddit}</span>
          {cancelled && (
            <span className="shrink-0 rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-ink-soft">
              {t.pipeline.cancelled}
            </span>
          )}
          <span className="shrink-0 rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-ink-soft">
            {t.pipeline.cycle} {progress.cycle}
          </span>
        </span>

        <div className="flex shrink-0 items-center gap-1">
          {running && onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="rounded-md px-2 py-0.5 text-xs text-ink-soft transition-colors hover:bg-surface-2 hover:text-danger"
            >
              {t.pipeline.cancel}
            </button>
          )}
          {!running && (
            <button
              type="button"
              onClick={() => clear(progress.runId)}
              aria-label={t.pipeline.discard}
              className="rounded-md p-1 text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink"
            >
              <X className="size-3.5" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      <div
        className={`mt-2.5 h-1.5 overflow-hidden rounded-full bg-surface-2 ${
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

      <p className="mt-2 font-mono text-[11px] tabular-nums text-ink-soft">
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

      {/* Un fallo se explica con el texto traducido de su código estable,
          nunca con el mensaje crudo de la excepción (AUD-003). */}
      {failed && (
        <p className="mt-1.5 text-xs text-danger">
          {scanErrorText(t, progress.errorCode, progress.retryAfterSeconds)}
        </p>
      )}

      {!failed && progress.persistError && (
        <div className="mt-1.5">
          <ErrorNotice code="persist_failed" detail={progress.persistError} tone="warn" />
        </div>
      )}
    </div>
  );
}
