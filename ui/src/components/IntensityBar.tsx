import { Explain } from "@/components/Explain";
import { useT } from "@/stores/settingsStore";
import { OPPORTUNITY_CLUSTER_THRESHOLD, type UrgencyTier } from "@/types/radar";

const FILL: Record<UrgencyTier, string> = {
  CRITICAL: "bg-critical",
  HIGH: "bg-high",
  MEDIUM: "bg-medium",
  LOW: "bg-low",
};

/**
 * Intensidad de un problema, de 0 a 100.
 *
 * Lleva una marca fija en el umbral de cualificación. Un 58 y un 62 se
 * parecen como números, pero uno queda fuera y el otro dentro: la marca lo
 * hace visible sin tener que recordar cuál era el corte.
 */
export function IntensityBar({
  score,
  tier,
  showScale = true,
}: {
  score: number;
  tier: UrgencyTier;
  showScale?: boolean;
}) {
  const t = useT();
  const clamped = Math.max(0, Math.min(100, score));

  return (
    <div className="flex flex-col gap-1">
      {showScale && (
        <div className="flex items-center justify-between text-xs text-ink-soft">
          <span className="inline-flex items-center gap-1">
            {t.radar.intensity}
            <Explain title={t.explain.intensity.title} body={t.explain.intensity.body} />
          </span>
          <span className="font-mono font-semibold tabular-nums text-ink">
            {clamped.toFixed(1)}
          </span>
        </div>
      )}

      <div
        className="relative h-2 overflow-hidden rounded-full bg-surface-2"
        role="meter"
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={t.radar.intensity}
      >
        <div
          className={`h-full rounded-full transition-[width] duration-500 ease-out ${FILL[tier]}`}
          style={{ width: `${clamped}%` }}
        />
        <div
          className="absolute inset-y-0 w-px bg-ink-faint"
          style={{ left: `${OPPORTUNITY_CLUSTER_THRESHOLD}%` }}
          aria-hidden="true"
          title={`${OPPORTUNITY_CLUSTER_THRESHOLD}`}
        />
      </div>
    </div>
  );
}
