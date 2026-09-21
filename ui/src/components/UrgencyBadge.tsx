import { URGENCY_LABELS, type UrgencyTier } from "@/types/radar";

const STYLES: Record<UrgencyTier, string> = {
  CRITICAL: "bg-[--color-urgency-critical] text-white",
  HIGH: "bg-[--color-urgency-high] text-black",
  MEDIUM: "bg-[--color-urgency-medium] text-black",
  LOW: "bg-[--color-urgency-low] text-white",
};

// El símbolo acompaña al color: quien no distingue rojo de naranja sigue
// pudiendo leer la urgencia.
const SYMBOLS: Record<UrgencyTier, string> = {
  CRITICAL: "!!!",
  HIGH: "!!",
  MEDIUM: "!",
  LOW: "·",
};

export function UrgencyBadge({ tier }: { tier: UrgencyTier }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${STYLES[tier]}`}
    >
      <span aria-hidden="true">{SYMBOLS[tier]}</span>
      {URGENCY_LABELS[tier]}
    </span>
  );
}
