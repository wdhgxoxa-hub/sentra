import { ScoreBreakdownBars } from "@/components/ScoreBreakdownBars";
import { UrgencyBadge } from "@/components/UrgencyBadge";
import { useClusterHistory, useOpportunityBoard } from "@/lib/queries";
import { useUiStore } from "@/stores/uiStore";

/** Ficha de una oportunidad: JTBD, matematica de la puntuacion y evidencia. */
export function OpportunityDetail() {
  const clusterKey = useUiStore((state) => state.selectedClusterKey);
  const board = useOpportunityBoard({ limit: 100 });
  const history = useClusterHistory(clusterKey);

  const cluster = board.data?.find((item) => item.clusterKey === clusterKey);

  if (!clusterKey) {
    return (
      <p className="text-sm text-[--color-ink-muted]">
        Selecciona una oportunidad en el radar para ver su ficha.
      </p>
    );
  }

  if (!cluster) {
    return <p className="text-sm text-[--color-ink-muted]">Cargando ficha...</p>;
  }

  return (
    <article className="flex flex-col gap-5">
      <header className="flex items-center gap-3">
        <h2 className="text-lg font-semibold">{cluster.label}</h2>
        <UrgencyBadge tier={cluster.urgencyTier} />
      </header>

      <section>
        <h3 className="mb-1 text-sm font-semibold">Jobs-To-Be-Done</h3>
        <p className="text-sm">{cluster.jobStatement}</p>
      </section>

      <section className="max-w-md">
        <h3 className="mb-2 text-sm font-semibold">Desglose de la puntuacion</h3>
        <ScoreBreakdownBars breakdown={cluster.breakdown} />
      </section>

      <section>
        <h3 className="mb-1 text-sm font-semibold">
          Evidencia ({cluster.evidence.length} citas)
        </h3>
        <ul className="flex flex-col gap-2">
          {cluster.evidence.map((quote) => (
            <li
              key={quote.signalId}
              className="border-l-2 border-[--color-border-subtle] pl-3 text-sm"
            >
              <p className="italic">{quote.quote}</p>
              <p className="text-xs text-[--color-ink-muted]">
                r/{quote.subreddit}, {quote.author}
              </p>
            </li>
          ))}
        </ul>
      </section>

      {cluster.currentSolutions.length > 0 && (
        <section>
          <h3 className="mb-1 text-sm font-semibold">Soluciones mencionadas</h3>
          <p className="text-sm">{cluster.currentSolutions.join(", ")}</p>
        </section>
      )}

      <section>
        <h3 className="mb-1 text-sm font-semibold">Evolucion</h3>
        <p className="text-sm text-[--color-ink-muted]">
          {history.data?.length ?? 0} lecturas registradas
        </p>
      </section>
    </article>
  );
}
