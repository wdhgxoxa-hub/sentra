import { useT } from "@/stores/settingsStore";
import type { EvidenceDataSource } from "@/types/radar";

/**
 * De dónde salen los datos de una pieza de evidencia (D-J): reales o de
 * demostración. Sin él, una cita inventada y una real se leerían igual.
 * `null` se dice «desconocida», nunca se supone.
 */
export function SourceBadge({ source }: { source: EvidenceDataSource | null }) {
  const t = useT();
  const estilo =
    source === "demo"
      ? { texto: t.source.demo, clase: "bg-warn/15 text-warn" }
      : source === "real"
        ? { texto: t.source.real, clase: "bg-surface-2 text-ink-soft" }
        : { texto: t.source.unknown, clase: "bg-surface-2 text-ink-faint" };

  return (
    <span
      className={`inline-flex shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${estilo.clase}`}
    >
      {estilo.texto}
    </span>
  );
}
