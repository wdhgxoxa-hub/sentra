import { Check, Copy, FileDown, FileText, Loader2, Quote as QuoteIcon } from "lucide-react";
import { useState } from "react";

import { ipc } from "@/lib/ipc";
import { useBlueprint } from "@/lib/queries";
import { useArchitectStore } from "@/stores/architectStore";
import { useSettingsStore, useT } from "@/stores/settingsStore";

/**
 * Especificación del proyecto (PRD).
 *
 * Va plegado y se redacta al abrirlo, no al entrar en la ficha: cuesta una
 * llamada al motor y la mayoría de las visitas son para mirar la evidencia,
 * no para decidir construir.
 *
 * El documento se muestra maquetado —jerarquía, listas, citas destacadas— y
 * se puede copiar en Markdown, que es como acaba en Notion, en un issue de
 * GitHub o en el correo a quien vaya a programarlo.
 */
export function BlueprintPanel({ clusterKey }: { clusterKey: string }) {
  const t = useT();
  const language = useSettingsStore((state) => state.language);
  const [abierto, setAbierto] = useState(false);
  const [copiado, setCopiado] = useState<"si" | "no" | null>(null);

  const doc = useBlueprint(clusterKey, language, abierto);

  const copiar = async (markdown: string) => {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopiado("si");
    } catch {
      // El portapapeles puede estar bloqueado segun donde se abra la ventana.
      // Decirlo es mejor que un boton que parece funcionar y no hace nada.
      setCopiado("no");
    }
    window.setTimeout(() => setCopiado(null), 2500);
  };

  return (
    <section className="rounded-card border border-accent/30 bg-accent-soft/40">
      <button
        type="button"
        onClick={() => setAbierto((previo) => !previo)}
        aria-expanded={abierto}
        className="flex w-full items-center gap-2.5 px-5 py-3.5 text-left text-sm font-semibold text-accent transition-colors hover:bg-accent-soft"
      >
        <FileText className="size-4 shrink-0" aria-hidden="true" />
        {abierto ? t.blueprint.close : t.blueprint.open}
      </button>

      {abierto && (
        <div className="border-t border-accent/20 px-5 pb-6 pt-5">
          {doc.isPending && (
            <p className="text-sm text-ink-faint">{t.blueprint.loading}</p>
          )}

          {doc.isError && (
            <p className="text-sm text-danger">
              {t.blueprint.error}: {String(doc.error)}
            </p>
          )}

          {doc.data && (
            <article className="enter flex flex-col gap-5">
              {/* La fuente de los datos va antes que nada (AUD-009): un PRD
                  sobre datos fabricados no puede leerse como uno real. */}
              <p
                className={`rounded-lg p-2.5 text-xs font-medium ${
                  doc.data.dataSource === "reddit"
                    ? "bg-surface text-ink-soft"
                    : "bg-warn/15 text-warn"
                }`}
              >
                {doc.data.sourceNotice}
              </p>

              <header className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="text-lg font-semibold">{doc.data.productName}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-ink-soft">
                    <span className="font-medium text-ink">
                      {t.blueprint.value}:
                    </span>{" "}
                    {doc.data.oneLiner}
                  </p>
                </div>

                <ExportarPdf clusterKey={clusterKey} />

                <button
                  type="button"
                  onClick={() => copiar(doc.data.markdown)}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium transition-colors hover:bg-surface-2"
                >
                  {copiado === "si" ? (
                    <Check className="size-3.5 text-ok" aria-hidden="true" />
                  ) : (
                    <Copy className="size-3.5" aria-hidden="true" />
                  )}
                  {copiado === "si"
                    ? t.blueprint.copied
                    : copiado === "no"
                      ? t.blueprint.copyFailed
                      : t.blueprint.copy}
                </button>
              </header>

              <Apartado titulo={t.blueprint.summary} texto={doc.data.executiveSummary} />
              <Apartado titulo={t.blueprint.problem} texto={doc.data.problem} />
              <Apartado titulo={t.blueprint.solution} texto={doc.data.solution} />

              <section>
                <h4 className="mb-2 text-sm font-semibold">{t.blueprint.mvp}</h4>
                <div className="grid gap-3 sm:grid-cols-2">
                  {doc.data.mvp.map((fase) => (
                    <div
                      key={fase.name}
                      className="rounded-lg border border-border bg-surface p-3"
                    >
                      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">
                        {fase.name}
                      </p>
                      <ul className="flex flex-col gap-1.5">
                        {fase.items.map((item) => (
                          <li
                            key={item}
                            className="flex gap-2 text-xs leading-relaxed text-ink-soft"
                          >
                            <span className="mt-1.5 size-1 shrink-0 rounded-full bg-accent" aria-hidden="true" />
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </section>

              <Apartado titulo={t.blueprint.fail} texto={doc.data.whyExistingFail} />
              <Apartado titulo={t.blueprint.money} texto={doc.data.monetisation} />

              {doc.data.evidence.length > 0 && (
                <section>
                  <h4 className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
                    <QuoteIcon className="size-3.5 text-ink-soft" aria-hidden="true" />
                    {t.blueprint.evidence}
                    <span className="text-xs font-normal text-ink-faint">
                      ({doc.data.distinctQuotes} {t.blueprint.quotes})
                    </span>
                  </h4>
                  <ul className="flex flex-col gap-2">
                    {doc.data.evidence.map((cita) => (
                      <li
                        key={cita.url + cita.quote.slice(0, 24)}
                        className="rounded-lg border-l-2 border-accent bg-surface px-3 py-2"
                      >
                        <p className="whitespace-pre-line text-xs italic leading-relaxed">
                          {cita.quote}
                        </p>
                        <p className="mt-1 font-mono text-[11px] text-ink-faint">
                          r/{cita.subreddit} · {cita.author}
                        </p>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              <p className="border-t border-border pt-3 text-[11px] leading-relaxed text-ink-faint">
                {t.blueprint.derived}
              </p>
            </article>
          )}
        </div>
      )}
    </section>
  );
}

type EstadoPdf =
  | { fase: "reposo" }
  | { fase: "generando" }
  | { fase: "guardado"; ruta: string }
  | { fase: "cancelado" }
  | { fase: "error" };

/**
 * Exporta el documento a PDF (AUD-008).
 *
 * Rust genera, pregunta dónde guardar y escribe; aquí solo se dispara y se
 * cuenta el resultado. El plan de Gemini entra si se generó en esta sesión.
 * Un fallo se muestra traducido, nunca con el texto crudo del error.
 */
function ExportarPdf({ clusterKey }: { clusterKey: string }) {
  const t = useT();
  const language = useSettingsStore((state) => state.language);
  const plan = useArchitectStore((state) => state.plans[clusterKey] ?? null);
  const [estado, setEstado] = useState<EstadoPdf>({ fase: "reposo" });

  const exportar = async () => {
    setEstado({ fase: "generando" });
    try {
      const ruta = await ipc.exportPdf(clusterKey, language, plan);
      setEstado(ruta ? { fase: "guardado", ruta } : { fase: "cancelado" });
    } catch (fallo) {
      console.error("[pdf] exportación fallida:", fallo);
      setEstado({ fase: "error" });
    }
  };

  return (
    <div className="flex shrink-0 flex-col items-end gap-1">
      <button
        type="button"
        onClick={exportar}
        disabled={estado.fase === "generando"}
        className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-on-accent transition-colors hover:bg-accent-hover disabled:opacity-50"
      >
        {estado.fase === "generando" ? (
          <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
        ) : (
          <FileDown className="size-3.5" aria-hidden="true" />
        )}
        {estado.fase === "generando" ? t.pdf.exporting : t.pdf.export}
      </button>
      <p className="max-w-xs text-right text-[11px] text-ink-faint" aria-live="polite">
        {estado.fase === "reposo" && (plan ? t.pdf.withPlan : t.pdf.withoutPlan)}
        {estado.fase === "guardado" && t.pdf.saved.replace("{path}", estado.ruta)}
        {estado.fase === "cancelado" && t.pdf.cancelled}
        {estado.fase === "error" && <span className="text-danger">{t.pdf.error}</span>}
      </p>
    </div>
  );
}

function Apartado({ titulo, texto }: { titulo: string; texto: string }) {
  return (
    <section>
      <h4 className="mb-1.5 text-sm font-semibold">{titulo}</h4>
      <p className="text-sm leading-relaxed text-ink-soft">{texto}</p>
    </section>
  );
}
