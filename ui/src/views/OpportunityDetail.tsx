import { Quote, TrendingUp, Wrench } from "lucide-react";

import { CommunityTags } from "@/components/CommunityTags";
import { Explain } from "@/components/Explain";
import { IntensityBar } from "@/components/IntensityBar";
import { ScoreBreakdownBars } from "@/components/ScoreBreakdownBars";
import { UrgencyBadge } from "@/components/UrgencyBadge";
import { ValidationControls } from "@/components/ValidationControls";
import { useClusterHistory, useOpportunityDetail } from "@/lib/queries";
import { useT } from "@/stores/settingsStore";
import { useUiStore } from "@/stores/uiStore";

/** Ficha de una oportunidad: qué necesita la gente, cuánto pesa y por qué. */
export function OpportunityDetail() {
  const t = useT();
  const clusterKey = useUiStore((state) => state.selectedClusterKey);
  const detail = useOpportunityDetail(clusterKey);
  const history = useClusterHistory(clusterKey);

  const cluster = detail.data;

  if (!clusterKey) {
    return (
      <p className="text-sm text-[--color-ink-soft]">{t.detail.selectPrompt}</p>
    );
  }
  if (detail.isPending) {
    return <p className="text-sm text-[--color-ink-faint]">{t.detail.loading}</p>;
  }
  if (!cluster) {
    return <p className="text-sm text-[--color-ink-soft]">{t.detail.gone}</p>;
  }

  return (
    <article className="flex max-w-3xl flex-col gap-6">
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-lg font-semibold">{cluster.label}</h2>
          <UrgencyBadge tier={cluster.urgencyTier} />
        </div>
        <CommunityTags subreddits={cluster.subreddits} max={6} />
        <IntensityBar
          score={cluster.breakdown.finalScore}
          tier={cluster.urgencyTier}
        />
      </header>

      <section className="rounded-[--radius-card] border border-[--color-border] bg-[--color-surface] p-4">
        <h3 className="mb-1.5 flex items-center gap-1.5 text-sm font-semibold">
          {t.detail.job}
          <Explain title={t.explain.jtbd.title} body={t.explain.jtbd.body} />
        </h3>
        <p className="text-sm leading-relaxed">{cluster.jobStatement}</p>
      </section>

      <ValidationControls cluster={cluster} />

      <section className="rounded-[--radius-card] border border-[--color-border] bg-[--color-surface] p-4">
        <h3 className="mb-3 text-sm font-semibold">{t.detail.breakdown}</h3>
        <ScoreBreakdownBars breakdown={cluster.breakdown} />
      </section>

      <section>
        <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
          <Quote className="size-4 text-[--color-ink-soft]" aria-hidden="true" />
          {t.detail.evidence}
          <span className="text-xs font-normal text-[--color-ink-faint]">
            ({cluster.evidence.length} {t.detail.quotes})
          </span>
        </h3>
        <ul className="flex flex-col gap-2">
          {cluster.evidence.map((quote) => (
            <li
              key={quote.signalId}
              className="rounded-[--radius-card] border-l-2 border-[--color-accent] bg-[--color-surface] py-2 pl-3 pr-3"
            >
              <p className="text-sm italic leading-relaxed">{quote.quote}</p>
              <p className="mt-1 flex items-center gap-2 text-[11px] text-[--color-ink-faint]">
                <span className="font-mono">r/{quote.subreddit}</span>
                <span aria-hidden="true">·</span>
                <span>{quote.author}</span>
              </p>
            </li>
          ))}
        </ul>
      </section>

      {cluster.currentSolutions.length > 0 && (
        <section>
          <h3 className="mb-1.5 flex items-center gap-1.5 text-sm font-semibold">
            <Wrench className="size-4 text-[--color-ink-soft]" aria-hidden="true" />
            {t.detail.solutions}
          </h3>
          <p className="text-sm">{cluster.currentSolutions.join(", ")}</p>
        </section>
      )}

      <section>
        <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
          <TrendingUp className="size-4 text-[--color-ink-soft]" aria-hidden="true" />
          {t.detail.evolution}
        </h3>

        {history.data && history.data.length > 1 ? (
          <ol className="flex flex-col gap-1">
            {history.data.slice(0, 8).map((point) => (
              <li
                key={point.id}
                className="flex items-center gap-3 rounded-lg px-2 py-1.5 font-mono text-xs tabular-nums hover:bg-[--color-surface-2]"
              >
                <span className="text-[--color-ink-faint]">
                  {point.createdAt.slice(0, 16)}
                </span>
                <span className="w-14 text-right font-semibold">
                  {point.finalScore.toFixed(1)}
                </span>
                <span className="flex-1">
                  <span
                    className="block h-1 rounded-full bg-[--color-accent]"
                    style={{ width: `${Math.min(100, point.finalScore)}%` }}
                  />
                </span>
                <span className="text-[--color-ink-soft]">
                  {point.mentionCount}m / {point.communityCount}c
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-xs leading-relaxed text-[--color-ink-soft]">
            {t.detail.noEvolution}
          </p>
        )}
      </section>
    </article>
  );
}
