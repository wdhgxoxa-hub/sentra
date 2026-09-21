import { ScoreBreakdownBars } from "@/components/ScoreBreakdownBars";
import { ValidationControls } from "@/components/ValidationControls";
import { UrgencyBadge } from "@/components/UrgencyBadge";
import { VALIDATION_LABELS } from "@/types/radar";
import { useClusterHistory, useOpportunityDetail } from "@/lib/queries";
import { useUiStore } from "@/stores/uiStore";

/** Ficha de una oportunidad: JTBD, matematica de la puntuacion y evidencia. */
export function OpportunityDetail() {
  const clusterKey = useUiStore((state) => state.selectedClusterKey);
  // Consulta dirigida en lugar de filtrar el tablero entero en el cliente.
  const detail = useOpportunityDetail(clusterKey);
  const history = useClusterHistory(clusterKey);

  const cluster = detail.data;

  if (!clusterKey) {
    return (
      <p className="text-sm text-[--color-ink-muted]">
        Selecciona una oportunidad en el radar para ver su ficha.
      </p>
    );
  }

  if (detail.isPending) {
    return <p className="text-sm text-[--color-ink-muted]">Cargando ficha...</p>;
  }

  if (!cluster) {
    return (
      <p className="text-sm text-[--color-ink-muted]">
        Esa oportunidad ya no esta en el almacen.
      </p>
    );
  }

  return (
    <article className="flex flex-col gap-5">
      <header className="flex items-center gap-3">
        <h2 className="text-lg font-semibold">{cluster.label}</h2>
        <UrgencyBadge tier={cluster.urgencyTier} />
        <span className="rounded-full border border-[--color-border-subtle] px-2 py-0.5 text-xs">
          {VALIDATION_LABELS[cluster.validationStatus]}
        </span>
      </header>

      <ValidationControls cluster={cluster} />

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
        {history.data && history.data.length > 1 ? (
          <ul className="flex flex-col gap-1 text-sm">
            {history.data.slice(0, 6).map((point) => (
              <li key={point.id} className="flex gap-3 font-mono tabular-nums">
                <span className="text-[--color-ink-muted]">
                  {point.createdAt.slice(0, 16)}
                </span>
                <span>{point.finalScore.toFixed(1)} pts</span>
                <span className="text-[--color-ink-muted]">
                  {point.mentionCount}m / {point.communityCount}c
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-[--color-ink-muted]">
            Una sola lectura por ahora. La evolucion aparece cuando el mismo
            problema se detecta en escaneos sucesivos.
          </p>
        )}
      </section>
    </article>
  );
}
