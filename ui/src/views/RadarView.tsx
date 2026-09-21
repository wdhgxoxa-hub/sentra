import { UrgencyBadge } from "@/components/UrgencyBadge";
import { useOpportunityBoard, useRadarFeed } from "@/lib/queries";
import { useUiStore } from "@/stores/uiStore";
import { OPPORTUNITY_CLUSTER_THRESHOLD } from "@/types/radar";

/**
 * Dashboard principal.
 *
 * Dos niveles, deliberadamente separados: arriba las oportunidades
 * consolidadas (lo que merece producto) y abajo el feed de quejas sueltas
 * (lo que esta pasando). Mezclarlos fue el error que causo la deuda D6.
 */
export function RadarViewPage() {
  const urgencyFilter = useUiStore((state) => state.urgencyFilter);
  const minScore = useUiStore((state) => state.minScore);
  const qualifiedOnly = useUiStore((state) => state.qualifiedOnly);
  const selectClusterKey = useUiStore((state) => state.selectClusterKey);
  const setView = useUiStore((state) => state.setView);

  const tiers = urgencyFilter.length ? urgencyFilter : undefined;
  const board = useOpportunityBoard({ limit: 20, qualifiedOnly, urgencyTiers: tiers });
  const feed = useRadarFeed({ limit: 50, minScore, urgencyTiers: tiers });

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="oportunidades">
        <h2 id="oportunidades" className="mb-2 text-base font-semibold">
          Oportunidades consolidadas{" "}
          <span className="text-sm font-normal text-[--color-ink-muted]">
            (corte {OPPORTUNITY_CLUSTER_THRESHOLD})
          </span>
        </h2>

        {board.isPending && (
          <p className="text-sm text-[--color-ink-muted]">Cargando...</p>
        )}
        {board.isError && (
          <p className="text-sm text-[--color-urgency-critical]">
            No se pudo cargar el tablero.
          </p>
        )}
        {board.data?.length === 0 && (
          <p className="text-sm text-[--color-ink-muted]">
            Aun no hay ningun problema recurrente que supere el corte. Un dolor
            necesita repetirse en varias comunidades para cualificar.
          </p>
        )}

        <ul className="grid gap-3 md:grid-cols-2">
          {board.data?.map((cluster) => (
            <li
              key={cluster.id}
              className="rounded-lg border border-[--color-border-subtle] bg-[--color-surface-raised] p-3"
            >
              <button
                type="button"
                className="w-full text-left"
                onClick={() => {
                  selectClusterKey(cluster.clusterKey);
                  setView("opportunity");
                }}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{cluster.label}</span>
                  <UrgencyBadge tier={cluster.urgencyTier} />
                </div>
                <p className="mt-1 text-sm text-[--color-ink-muted]">
                  {cluster.mentionCount} menciones en {cluster.communityCount}{" "}
                  comunidades, {cluster.breakdown.finalScore.toFixed(1)} pts
                </p>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="feed">
        <h2 id="feed" className="mb-2 text-base font-semibold">
          Actividad reciente
        </h2>
        <ul className="divide-y divide-[--color-border-subtle]">
          {feed.data?.map((entry) => (
            <li key={entry.signalId} className="flex items-start gap-3 py-2">
              <UrgencyBadge tier={entry.urgencyTier} />
              <div className="min-w-0">
                <p className="truncate text-sm">
                  {entry.postTitle ?? entry.content}
                </p>
                <p className="text-xs text-[--color-ink-muted]">
                  r/{entry.subredditName}, {entry.finalScore.toFixed(1)} pts
                </p>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
