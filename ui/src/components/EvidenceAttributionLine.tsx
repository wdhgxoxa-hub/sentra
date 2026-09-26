import { DireccionDelOriginal } from "@/components/DireccionDelOriginal";
import type { EvidenceAttribution } from "@/types/radar";

/**
 * Atribución de una pieza de evidencia: insignia de la plataforma, sitio y
 * dirección del original (R5; los términos de Stack Exchange la exigen
 * visible). Toda vista que enseñe evidencia multifuente la usa. D-M12: la
 * dirección se ve sin la cuenta del autor y se copia completa. Con
 * licencia (Stack Exchange, CC BY-SA 4.0) se dice cuál y dónde leerla; el
 * autor se ve siguiendo la URL del original, nunca aquí (R9).
 */
export function EvidenceAttributionLine({ attribution }: { attribution: EvidenceAttribution }) {
  return (
    <p className="flex flex-wrap items-center gap-1.5 text-xs text-ink-soft">
      <span className="rounded-full border border-border px-2 py-0.5 font-medium text-ink">
        {attribution.badge}
      </span>
      <span>{attribution.site}</span>
      <span aria-hidden="true">·</span>
      <DireccionDelOriginal url={attribution.url} />
      {attribution.license && (
        <>
          <span aria-hidden="true">·</span>
          <span title={attribution.licenseUrl ?? undefined}>{attribution.license}</span>
          {attribution.licenseUrl && (
            <span className="select-all break-all text-ink-faint" data-ajeno="">{attribution.licenseUrl}</span>
          )}
        </>
      )}
    </p>
  );
}
