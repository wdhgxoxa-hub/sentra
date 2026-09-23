import { ArrowRight, MessageSquare, Users } from "lucide-react";

import { CommunityTags } from "@/components/CommunityTags";
import { IntensityBar } from "@/components/IntensityBar";
import { SourceBadge } from "@/components/SourceBadge";
import { UrgencyBadge } from "@/components/UrgencyBadge";
import { useT } from "@/stores/settingsStore";
import type { OpportunityCluster } from "@/types/radar";

const STATUS_STYLES: Record<string, string> = {
  new: "bg-surface-2 text-ink-soft",
  triaged: "bg-medium-soft text-medium-ink",
  validated: "bg-ok/15 text-ok",
  rejected: "bg-surface-2 text-ink-faint line-through",
  shipped: "bg-accent-soft text-accent",
};

/**
 * Tarjeta de una oportunidad.
 *
 * El orden lo decide qué hace falta para actuar: primero el problema en
 * palabras llanas, luego dónde se repite y con cuánta fuerza, y al final el
 * botón. La puntuación no va arriba del todo a propósito: un número sin el
 * problema al lado no dice nada.
 */
export function OpportunityCard({
  cluster,
  onOpen,
}: {
  cluster: OpportunityCluster;
  onOpen: () => void;
}) {
  const t = useT();
  const statusLabel =
    t.validation[cluster.validationStatus as keyof typeof t.validation];

  return (
    <article className="enter group flex flex-col gap-3 rounded-card border border-border bg-surface p-5 shadow-[var(--shadow-card)] transition-all hover:border-border-strong hover:shadow-[var(--shadow-pop)]">
      <header className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 flex-1 text-sm font-semibold leading-snug">
          {cluster.label}
        </h3>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <UrgencyBadge tier={cluster.urgencyTier} />
          <SourceBadge source={cluster.dataSource} />
        </div>
      </header>

      {cluster.jobStatement && (
        <p className="line-clamp-2 text-xs leading-relaxed text-ink-soft">
          {cluster.jobStatement}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-ink-soft">
        <span className="inline-flex items-center gap-1">
          <MessageSquare className="size-3.5" aria-hidden="true" />
          <strong className="font-mono tabular-nums text-ink">
            {cluster.mentionCount}
          </strong>
          {t.radar.mentions}
        </span>
        <span className="inline-flex items-center gap-1">
          <Users className="size-3.5" aria-hidden="true" />
          <strong className="font-mono tabular-nums text-ink">
            {cluster.communityCount}
          </strong>
          {t.radar.communities}
        </span>
      </div>

      <CommunityTags subreddits={cluster.subreddits} />

      <IntensityBar
        score={cluster.breakdown.finalScore}
        tier={cluster.urgencyTier}
      />

      <footer className="flex items-center justify-between gap-2 pt-1">
        <span
          className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
            STATUS_STYLES[cluster.validationStatus] ?? STATUS_STYLES.new
          }`}
        >
          {statusLabel}
        </span>

        <button
          type="button"
          onClick={onOpen}
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-accent transition-colors hover:bg-accent-soft"
        >
          {t.radar.validate}
          <ArrowRight
            className="size-3.5 transition-transform group-hover:translate-x-0.5"
            aria-hidden="true"
          />
        </button>
      </footer>
    </article>
  );
}
