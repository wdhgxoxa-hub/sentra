import { Radar as RadarIcon } from "lucide-react";

import { Explain } from "@/components/Explain";
import { OpportunityCard } from "@/components/OpportunityCard";
import { UrgencyBadge } from "@/components/UrgencyBadge";
import { useOpportunityBoard, useRadarFeed } from "@/lib/queries";
import { useT } from "@/stores/settingsStore";
import { useUiStore } from "@/stores/uiStore";

/**
 * Dashboard principal.
 *
 * Dos niveles, deliberadamente separados: arriba los problemas consolidados
 * (lo que merece construir algo) y abajo el goteo de quejas sueltas (lo que
 * está pasando). Mezclarlos fue el error que dejó el radar vacío durante
 * varias fases, porque el corte de una oportunidad no es alcanzable por un
 * mensaje solo.
 */
export function RadarViewPage() {
  const t = useT();
  const urgencyFilter = useUiStore((state) => state.urgencyFilter);
  const minScore = useUiStore((state) => state.minScore);
  const qualifiedOnly = useUiStore((state) => state.qualifiedOnly);
  const selectClusterKey = useUiStore((state) => state.selectClusterKey);
  const setView = useUiStore((state) => state.setView);

  const tiers = urgencyFilter.length ? urgencyFilter : undefined;
  const board = useOpportunityBoard({ limit: 24, qualifiedOnly, urgencyTiers: tiers });
  const feed = useRadarFeed({ limit: 40, minScore, urgencyTiers: tiers });

  const abrir = (clusterKey: string) => {
    selectClusterKey(clusterKey);
    setView("opportunity");
  };

  return (
    <div className="flex flex-col gap-8">
      <section aria-labelledby="oportunidades">
        <header className="mb-3">
          <h2
            id="oportunidades"
            className="flex items-center gap-2 text-base font-semibold"
          >
            <RadarIcon className="size-4 text-[--color-accent]" aria-hidden="true" />
            {t.radar.title}
            <Explain
              title={t.explain.signalVsCluster.title}
              body={t.explain.signalVsCluster.body}
            />
          </h2>
          <p className="mt-0.5 text-xs text-[--color-ink-soft]">
            {t.radar.subtitle}
          </p>
        </header>

        {board.isPending && (
          <p className="text-sm text-[--color-ink-faint]">{t.radar.loading}</p>
        )}
        {board.isError && (
          <p className="text-sm text-[--color-danger]">{t.radar.error}</p>
        )}

        {board.data?.length === 0 && (
          <div className="rounded-[--radius-card] border border-dashed border-[--color-border] p-8 text-center">
            <p className="text-sm font-medium">{t.radar.empty}</p>
            <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-[--color-ink-soft]">
              {t.radar.emptyHint}
            </p>
          </div>
        )}

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {board.data?.map((cluster) => (
            <OpportunityCard
              key={cluster.id}
              cluster={cluster}
              onOpen={() => abrir(cluster.clusterKey)}
            />
          ))}
        </div>
      </section>

      <section aria-labelledby="feed">
        <header className="mb-3">
          <h2 id="feed" className="text-base font-semibold">
            {t.radar.feedTitle}
          </h2>
          <p className="mt-0.5 text-xs text-[--color-ink-soft]">
            {t.radar.feedSubtitle}
          </p>
        </header>

        <ul className="divide-y divide-[--color-border] rounded-[--radius-card] border border-[--color-border] bg-[--color-surface]">
          {feed.data?.map((entry) => (
            <li
              key={entry.signalId}
              className="flex items-start gap-3 px-3 py-2.5 transition-colors hover:bg-[--color-surface-2]"
            >
              <UrgencyBadge tier={entry.urgencyTier} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm">
                  {entry.postTitle ?? entry.content}
                </p>
                <p className="mt-0.5 flex items-center gap-2 text-[11px] text-[--color-ink-faint]">
                  <span className="font-mono">r/{entry.subredditName}</span>
                  <span aria-hidden="true">·</span>
                  <span className="font-mono tabular-nums">
                    {entry.finalScore.toFixed(1)} {t.radar.points}
                  </span>
                </p>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
