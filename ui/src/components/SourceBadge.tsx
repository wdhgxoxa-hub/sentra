import { useT } from "@/stores/settingsStore";
import type { DataSource, EvidenceDataSource } from "@/types/radar";

/**
 * De dónde salen los datos de un registro (D-J).
 *
 * Toda vista que lista registros de varias ejecuciones lo muestra con este
 * componente: sin él, una cita de demostración y una de Reddit se leían igual.
 * `null` es una fila anterior a la migración 007 cuya ejecución no lo
 * registró: se dice «desconocida», nunca se supone.
 */
export function SourceBadge({ source }: { source: DataSource | EvidenceDataSource | null }) {
  const t = useT();
  const estilo =
    source === "demo"
      ? { texto: t.source.demo, clase: "bg-warn/15 text-warn" }
      : source === "reddit"
        ? { texto: t.source.reddit, clase: "bg-surface-2 text-ink-soft" }
        : source === "real"
          ? { texto: t.source.real, clase: "bg-surface-2 text-ink-soft" }
          : { texto: t.source.unknown, clase: "bg-surface-2 text-ink-faint" };

  return (
    <span
      className={`inline-flex shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${estilo.clase}`}
    >
      {estilo.texto}
    </span>
  );
}
