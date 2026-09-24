import { useState } from "react";
import { CheckCircle2, FileDown } from "lucide-react";

import { ErrorNotice } from "@/components/ErrorNotice";
import { comoError } from "@/lib/errors";
import { useExportDocument } from "@/lib/queries";
import { useSettingsStore, useT } from "@/stores/settingsStore";
import type { DocumentFormat, DocumentKind, JudgeVerdict } from "@/types/radar";

const FORMATOS: DocumentFormat[] = ["pdf", "md"];

/**
 * Exportación del dossier y del plan de un veredicto (Fase E).
 *
 * El dossier existe para cualquier veredicto. El plan solo si el juez dice
 * Construir; para el resto hay que forzarlo a sabiendas, y el documento
 * lleva la advertencia en cada página. Se dice cuántas llamadas al modelo
 * costó cada exportación (0 = se reutilizó lo ya generado).
 */
export function DocumentActions({ v }: { v: JudgeVerdict }) {
  const t = useT();
  const language = useSettingsStore((s) => s.language);
  const exportar = useExportDocument();
  const [forzar, setForzar] = useState(false);
  const recomendado = v.verdict === "CONSTRUIR";
  const planPermitido = recomendado || forzar;
  const enCurso = exportar.isPending ? exportar.variables : null;

  const boton = (kind: DocumentKind, format: DocumentFormat, disabled = false) => (
    <button
      key={`${kind}-${format}`}
      type="button"
      disabled={disabled || exportar.isPending}
      onClick={() =>
        exportar.mutate({ verdictId: v.id, kind, format, language, force: kind === "plan" && !recomendado })
      }
      className="flex items-center gap-1 rounded-lg border border-border px-2 py-1 text-[11px] transition-colors hover:bg-surface-2 disabled:opacity-40"
    >
      <FileDown className="size-3" aria-hidden="true" />
      {t.documents.format[format]}
    </button>
  );

  return (
    <section className="mt-3 border-t border-border pt-3">
      <h4 className="mb-1 text-xs font-semibold">{t.documents.title}</h4>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] text-ink-soft">{t.documents.kind.dossier}</span>
        {FORMATOS.map((f) => boton("dossier", f))}
        <span className="ml-2 text-[11px] text-ink-soft">{t.documents.kind.plan}</span>
        {FORMATOS.map((f) => boton("plan", f, !planPermitido))}
      </div>
      {!recomendado && (
        <label className="mt-1 flex items-start gap-2 text-[11px] text-warn">
          <input type="checkbox" checked={forzar} onChange={(e) => setForzar(e.target.checked)} />
          {t.documents.forcePlan.replace("{verdict}", t.judge.verdict[v.verdict])}
        </label>
      )}
      {enCurso && (
        <p className="mt-1 text-[11px] text-ink-faint">
          {t.documents.generating.replace("{kind}", t.documents.kind[enCurso.kind])}
        </p>
      )}
      {exportar.isError && <ErrorNotice {...comoError(exportar.error)} title={t.documents.failed} />}
      {exportar.isSuccess && exportar.data === null && (
        <p className="mt-1 text-[11px] text-ink-faint">{t.documents.cancelled}</p>
      )}
      {exportar.isSuccess && exportar.data && (
        <p className="mt-1 flex items-start gap-1 text-[11px] text-ok">
          <CheckCircle2 className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
          <span>
            {t.documents.saved.replace("{path}", exportar.data.path)}{" "}
            <span className="text-ink-faint">
              {exportar.data.llmCalls === null
                ? t.documents.callsUnknown
                : t.documents.calls.replace("{n}", String(exportar.data.llmCalls))}
            </span>
          </span>
        </p>
      )}
    </section>
  );
}
