import type { EvidenceAttribution } from "@/types/radar";

/**
 * Atribución de una pieza de evidencia: insignia de la plataforma, sitio y
 * URL del original en texto plano (R5; los términos de Stack Exchange la
 * exigen visible). Toda vista que enseñe evidencia multifuente la usa; la
 * URL es seleccionable porque la ventana no abre enlaces externos.
 */
export function EvidenceAttributionLine({ attribution }: { attribution: EvidenceAttribution }) {
  return (
    <p className="flex flex-wrap items-center gap-1.5 text-[11px] text-ink-soft">
      <span className="rounded-full border border-border px-2 py-0.5 font-medium text-ink">
        {attribution.badge}
      </span>
      <span>{attribution.site}</span>
      <span aria-hidden="true">·</span>
      <span className="select-all break-all">{attribution.url}</span>
    </p>
  );
}
