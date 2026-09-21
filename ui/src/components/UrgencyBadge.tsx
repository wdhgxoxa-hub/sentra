import { useT } from "@/stores/settingsStore";
import type { UrgencyTier } from "@/types/radar";

const STYLES: Record<UrgencyTier, string> = {
  CRITICAL: "bg-[--color-critical-soft] text-[--color-critical] ring-[--color-critical]/30",
  HIGH: "bg-[--color-high-soft] text-[--color-high] ring-[--color-high]/30",
  MEDIUM: "bg-[--color-medium-soft] text-[--color-medium] ring-[--color-medium]/30",
  LOW: "bg-[--color-low-soft] text-[--color-low] ring-[--color-low]/30",
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
