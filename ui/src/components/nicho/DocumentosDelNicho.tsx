import { CheckCircle2, FileDown } from "lucide-react";
import { useState } from "react";

import { AccionPrincipal, Aviso, BotonSecundario, VerDetalle } from "@/components/comunes/Comunes";
import { comoError } from "@/lib/errors";
import { useDocumentsStatus, useExportDocument } from "@/lib/queries";
import type { NichoEnPantalla } from "@/modos/tipos";
import { useSettingsStore, useT } from "@/stores/settingsStore";
import type { DocumentFormat, DocumentKind } from "@/types/radar";

/** «Dossier guardado: se abre sin gastar», para la tarjeta del nicho en el Radar. */
export function DossierGuardado({ nicho }: { nicho: NichoEnPantalla }) {
  const t = useT();
  const idioma = useSettingsStore((s) => s.language);
  const estado = useDocumentsStatus(nicho.id);
  if (!estado.data?.dossier[idioma]) return null;
  return (
    <p className="flex items-center gap-1.5 text-sm text-ok">
      <CheckCircle2 className="size-4" aria-hidden="true" />
      {t.radar.documentoGuardado}
    </p>
  );
}

/**
 * Dossier y plan de un nicho, siempre a la vista (Fase 2): si ya están
 * guardados (se abren sin gastar) y, si no, lo que cuesta generarlos, dicho
 * ANTES de pulsar. El plan de un nicho que el juez no manda construir solo se
 * genera marcándolo a sabiendas, y lo dice en cada página.
 */
export function DocumentosDelNicho({ nicho }: { nicho: NichoEnPantalla }) {
  const t = useT();
  const idioma = useSettingsStore((s) => s.language);
  const estado = useDocumentsStatus(nicho.id);
  const exportar = useExportDocument();
  const [forzarPlan, setForzarPlan] = useState(false);
  const recomendado = nicho.veredicto === "CONSTRUIR";

  const guardar = (kind: DocumentKind, format: DocumentFormat) =>
    exportar.mutate({ verdictId: nicho.id, kind, format, language: idioma, force: kind === "plan" && !recomendado });
  const guardado = (kind: DocumentKind) => estado.data?.[kind][idioma] === true;

  const tarjeta = (kind: DocumentKind) => {
    const bloqueado = kind === "plan" && !recomendado && !forzarPlan;
    return (
      <section
        data-documento={kind}
        className={`flex flex-col gap-3 rounded-card border bg-surface p-5 shadow-card ${kind === "dossier" ? "border-accent/40" : "border-border"}`}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-semibold">{kind === "dossier" ? t.nicho.dossier : t.nicho.plan}</h2>
          <span
            className={`rounded-full px-3 py-1 text-[13px] font-semibold ${guardado(kind) ? "bg-ok/10 text-ok" : "bg-surface-2 text-ink-soft"}`}
          >
            {guardado(kind) ? t.nicho.guardado : t.nicho.sinGenerar}
          </span>
        </div>
        <p className="text-sm text-ink-soft">{kind === "dossier" ? t.nicho.dossierExplica : t.nicho.planExplica}</p>
        {kind === "plan" && !recomendado && (
          <>
            <p className="text-sm text-warn">{t.nicho.planNoRecomendado}</p>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={forzarPlan} onChange={(e) => setForzarPlan(e.target.checked)} />
              {t.nicho.generarIgual}
            </label>
          </>
        )}
        <div className="flex flex-wrap gap-2">
          {kind === "dossier" ? (
            <AccionPrincipal onClick={() => guardar("dossier", "pdf")} disabled={exportar.isPending}>
              <FileDown className="size-4" aria-hidden="true" />
              {t.nicho.guardarPdf}
            </AccionPrincipal>
          ) : (
            <BotonSecundario onClick={() => guardar("plan", "pdf")} disabled={bloqueado || exportar.isPending}>
              <FileDown className="size-4" aria-hidden="true" />
              {t.nicho.guardarPdf}
            </BotonSecundario>
          )}
          <BotonSecundario onClick={() => guardar(kind, "md")} disabled={bloqueado || exportar.isPending}>
            {t.nicho.guardarMd}
          </BotonSecundario>
        </div>
        {!guardado(kind) && <p className="text-[13px] text-ink-faint">{t.nicho.coste}</p>}
      </section>
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 lg:grid-cols-2">
        {tarjeta("dossier")}
        {tarjeta("plan")}
      </div>
      {exportar.isPending && <Aviso tono="info" titulo={t.nicho.generando} />}
      {exportar.isSuccess && exportar.data === null && <p className="text-sm text-ink-faint">{t.nicho.noSeGuardo}</p>}
      {exportar.isSuccess && exportar.data && (
        <Aviso tono="bien" titulo={t.nicho.guardadoEn.replace("{ruta}", exportar.data.path)} />
      )}
      {exportar.isError && (
        <>
          <Aviso tono="mal" titulo={t.nicho.fallo}>
            {t.errors[comoError(exportar.error).code as keyof typeof t.errors] ?? t.comun.algoFallo}
          </Aviso>
          <VerDetalle>
            <p className="font-mono text-[13px] text-ink-soft">{comoError(exportar.error).detail}</p>
          </VerDetalle>
        </>
      )}
    </div>
  );
}
