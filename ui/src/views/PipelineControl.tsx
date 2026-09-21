import { Pause, Play, Plus, Zap } from "lucide-react";
import { useState } from "react";

import { PipelineGraph } from "@/components/PipelineGraph";
import { ScanProgressBar } from "@/components/ScanProgressBar";
import {
  useCancelScan,
  useRuns,
  useSubreddits,
  useTriggerScan,
  useUpsertSubreddit,
} from "@/lib/queries";
import { useProgressStore } from "@/stores/progressStore";
import { useT } from "@/stores/settingsStore";
import type { ListingSort } from "@/types/radar";

const LISTINGS: ListingSort[] = ["new", "hot", "top", "rising"];

const RUN_STATUS_STYLES: Record<string, string> = {
  completed: "text-[--color-ok]",
  running: "text-[--color-accent]",
  failed: "text-[--color-danger]",
  cancelled: "text-[--color-ink-faint]",
};

/** Centro de control: lanzar escaneos y ver el motor trabajar. */
export function PipelineControl() {
  const t = useT();
  const subreddits = useSubreddits();
  const runs = useRuns(20);
  const scan = useTriggerScan();
  const cancelar = useCancelScan();
  const guardar = useUpsertSubreddit();

  const activos = useProgressStore((state) => Object.values(state.runs));
  const limpiar = useProgressStore((state) => state.clearFinished);

  const [name, setName] = useState("");
  const [listing, setListing] = useState<ListingSort>("new");
  const [tags, setTags] = useState("");

  const alta = (event: React.FormEvent) => {
    event.preventDefault();
    const limpio = name.trim();
    if (!limpio) return;

    guardar.mutate(
      {
        name: limpio,
        listing,
        tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean),
      },
      {
        onSuccess: () => {
          setName("");
          setTags("");
        },
      },
    );
  };

  const campo =
    "rounded-lg border border-[--color-border] bg-[--color-surface-2] px-3 py-1.5 text-sm transition-colors focus:border-[--color-accent]";

  return (
    <div className="flex flex-col gap-8">
      <header>
        <h2 className="text-base font-semibold">{t.pipeline.title}</h2>
        <p className="mt-0.5 text-xs text-[--color-ink-soft]">
          {t.pipeline.subtitle}
        </p>
      </header>

      {/* El recorrido del motor, siempre visible: explica qué va a pasar
          antes de pulsar, no solo mientras pasa. */}
      <section className="rounded-[--radius-card] border border-[--color-border] bg-[--color-surface] p-4">
        <PipelineGraph
          completed={activos[0]?.completed ?? []}
          current={activos[0]?.currentNode ?? null}
        />
      </section>

      {activos.length > 0 && (
        <section aria-labelledby="progreso">
          <div className="mb-2 flex items-center justify-between">
            <h3 id="progreso" className="text-sm font-semibold">
              {t.pipeline.running}
            </h3>
            <button
              type="button"
              onClick={limpiar}
              className="text-xs text-[--color-ink-faint] transition-colors hover:text-[--color-ink]"
            >
              {t.pipeline.clearFinished}
            </button>
          </div>
          <div className="flex flex-col gap-2">
            {activos.map((progreso) => (
              <ScanProgressBar
                key={progreso.runId}
                progress={progreso}
                onCancel={() => cancelar.mutate(progreso.runId)}
              />
            ))}
          </div>
        </section>
      )}

      <section aria-labelledby="comunidades">
        <h3 id="comunidades" className="mb-2 text-sm font-semibold">
          {t.pipeline.watched}
        </h3>

        <form
          onSubmit={alta}
          className="mb-3 flex flex-wrap items-end gap-2 rounded-[--radius-card] border border-[--color-border] bg-[--color-surface] p-3"
        >
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-[--color-ink-soft]">
              {t.pipeline.subreddit}
            </span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t.pipeline.addPlaceholder}
              className={`${campo} w-36`}
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-[--color-ink-soft]">
              {t.pipeline.order}
            </span>
            <select
              value={listing}
              onChange={(event) => setListing(event.target.value as ListingSort)}
              className={campo}
            >
              {LISTINGS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-1 flex-col gap-1">
            <span className="text-[11px] text-[--color-ink-soft]">
              {t.pipeline.tagsLabel}
            </span>
            <input
              value={tags}
              onChange={(event) => setTags(event.target.value)}
              placeholder={t.pipeline.tagsPlaceholder}
              className={`${campo} w-full`}
            />
          </label>

          <button
            type="submit"
            disabled={guardar.isPending || !name.trim()}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[--color-accent] px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-[--color-accent-hover] disabled:opacity-40"
          >
            <Plus className="size-3.5" aria-hidden="true" />
            {guardar.isPending ? t.pipeline.saving : t.pipeline.watch}
          </button>
        </form>

        <ul className="flex flex-col gap-2">
          {subreddits.data?.map((item) => (
            <li
              key={item.subredditId}
              className="flex items-center justify-between gap-3 rounded-[--radius-card] border border-[--color-border] bg-[--color-surface] px-3 py-2.5"
            >
              <div className="min-w-0">
                <p className="flex items-center gap-2 font-mono text-sm">
                  r/{item.name}
                  <span
                    className={`size-1.5 rounded-full ${
                      item.status === "active"
                        ? "bg-[--color-ok]"
                        : "bg-[--color-ink-faint]"
                    }`}
                    aria-hidden="true"
                  />
                </p>
                <p className="mt-0.5 text-[11px] text-[--color-ink-faint]">
                  {t.pipeline.lastRun}: {item.lastRunStatus ?? t.pipeline.never}
                </p>
              </div>

              <div className="flex shrink-0 gap-1.5">
                <button
                  type="button"
                  disabled={guardar.isPending}
                  onClick={() =>
                    guardar.mutate({
                      name: item.name,
                      status: item.status === "active" ? "paused" : "active",
                    })
                  }
                  className="inline-flex items-center gap-1 rounded-lg border border-[--color-border] px-2.5 py-1.5 text-xs transition-colors hover:bg-[--color-surface-2] disabled:opacity-40"
                >
                  {item.status === "active" ? (
                    <>
                      <Pause className="size-3" aria-hidden="true" />
                      {t.pipeline.pause}
                    </>
                  ) : (
                    <>
                      <Play className="size-3" aria-hidden="true" />
                      {t.pipeline.activate}
                    </>
                  )}
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
                  className="inline-flex items-center gap-1 rounded-lg bg-[--color-surface-2] px-2.5 py-1.5 text-xs font-medium transition-colors hover:bg-[--color-accent-soft] hover:text-[--color-accent] disabled:opacity-40"
                >
                  <Zap className="size-3" aria-hidden="true" />
                  {t.pipeline.scan}
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="historial">
        <h3 id="historial" className="mb-2 text-sm font-semibold">
          {t.pipeline.history}
        </h3>
        <div className="overflow-hidden rounded-[--radius-card] border border-[--color-border] bg-[--color-surface]">
          <table className="w-full text-sm">
            <thead className="border-b border-[--color-border] bg-[--color-surface-2] text-left text-[11px] uppercase tracking-wide text-[--color-ink-faint]">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t.pipeline.subreddit}
                </th>
                <th scope="col" className="px-2 py-2 font-medium">
                  {t.pipeline.colStatus}
                </th>
                <th scope="col" className="px-2 py-2 font-medium">
                  {t.pipeline.colRead}
                </th>
                <th scope="col" className="px-2 py-2 font-medium">
                  {t.pipeline.colQualified}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t.pipeline.colErrors}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[--color-border]">
              {runs.data?.map((run) => (
                <tr key={run.id} className="hover:bg-[--color-surface-2]">
                  <td className="px-3 py-2 font-mono text-xs">
                    r/{run.subredditName}
                  </td>
                  <td
                    className={`px-2 py-2 text-xs ${
                      RUN_STATUS_STYLES[run.status] ?? ""
                    }`}
                  >
                    {run.status}
                  </td>
                  <td className="px-2 py-2 font-mono text-xs tabular-nums">
                    {run.fetched}
                  </td>
                  <td className="px-2 py-2 font-mono text-xs tabular-nums">
                    {run.qualified}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs tabular-nums">
                    {run.errorCount > 0 ? (
                      <span className="text-[--color-warn]">{run.errorCount}</span>
                    ) : (
                      run.errorCount
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
