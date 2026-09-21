import { useT } from "@/stores/settingsStore";
import type { UrgencyTier } from "@/types/radar";

const STYLES: Record<UrgencyTier, string> = {
  CRITICAL: "bg-critical-soft text-critical-ink ring-critical/30",
  HIGH: "bg-high-soft text-high-ink ring-high/30",
  MEDIUM: "bg-medium-soft text-medium-ink ring-medium/30",
  LOW: "bg-low-soft text-low-ink ring-low/30",
};

// El número de barras acompaña al color: quien no distingue rojo de naranja
// sigue leyendo la urgencia de un vistazo.
const BARS: Record<UrgencyTier, number> = {
  CRITICAL: 4,
  HIGH: 3,
  MEDIUM: 2,
  LOW: 1,
};

export function UrgencyBadge({ tier }: { tier: UrgencyTier }) {
  const t = useT();
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${STYLES[tier]}`}
    >
      <span className="flex items-end gap-px" aria-hidden="true">
        {[1, 2, 3, 4].map((level) => (
          <span
            key={level}
            className="w-0.5 rounded-sm bg-current"
            style={{
              height: `${level * 2.5}px`,
              opacity: level <= BARS[tier] ? 1 : 0.25,
            }}
          />
        ))}
      </span>
      {t.urgency[tier]}
    </span>
  );
}
