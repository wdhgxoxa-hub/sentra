import { Play, Square } from "lucide-react";
import { useState } from "react";

import { ErrorNotice } from "@/components/ErrorNotice";
import { comoError } from "@/lib/errors";
import { useCancelScan, useTriggerMultiscan } from "@/lib/queries";
import { useMultiscanStore } from "@/stores/multiscanStore";
import { useT } from "@/stores/settingsStore";
import type { ScanProfileInput, SourceCard, SourceScanSummary } from "@/types/radar";

const IDIOMAS = ["en", "es"] as const;
/** La compuerta G6 mira 180 días; por defecto se trae un año (core/sources/profile.py). */
const VENTANA_POR_DEFECTO = 365;

function lineaDeFuente(t: ReturnType<typeof useT>, s: SourceScanSummary): string {
  const items = String(s.items);
  if (s.status === "running") return t.sources.sourceRunning.replace("{items}", items);
  if (s.status === "failed") return t.sources.sourceFailed.replace("{items}", items);
  if (s.stopReason === "cancelled") return t.sources.sourceCancelled.replace("{items}", items);
  if (s.stopReason) return t.sources.sourceStopped.replace("{items}", items);
  return t.sources.sourceDone.replace("{items}", items);
}

/**
 * Escaneo por perfil: tema (o modo descubrimiento), ventana e idiomas. El
 * progreso llega fuente a fuente; una que falla lo dice con su código y las
 * demás siguen.
 */
export function MultiscanPanel({ cards }: { cards: SourceCard[] }) {
  const t = useT();
  const escanear = useTriggerMultiscan();
  const cancelar = useCancelScan();
  const scan = useMultiscanStore((s) => s.scan);
  const reset = useMultiscanStore((s) => s.reset);
  const fail = useMultiscanStore((s) => s.fail);

  const [nombre, setNombre] = useState("");
  const [tema, setTema] = useState("");
  const [descubrimiento, setDescubrimiento] = useState(false);
  const [ventana, setVentana] = useState(VENTANA_POR_DEFECTO);
  const [idiomas, setIdiomas] = useState<string[]>([...IDIOMAS]);

  const palabras = tema.split(",").map((p) => p.trim()).filter(Boolean);
  // Las mismas reglas que valida el motor (ScanProfile): tema o descubrimiento.
  const valido =
    nombre.trim() !== "" &&
    idiomas.length > 0 &&
    ventana >= 1 &&
    descubrimiento !== palabras.length > 0;
  const enCurso = escanear.isPending || scan.status === "running";

  const lanzar = (event: React.FormEvent) => {
    event.preventDefault();
    if (!valido) return;
    const perfil: ScanProfileInput = {
      name: nombre.trim(),
      keywords: descubrimiento ? [] : palabras,
      discovery: descubrimiento,
      windowDays: ventana,
      languages: idiomas,
    };
    reset();
    escanear.mutate(perfil, { onError: (error) => fail(comoError(error)) });
  };

  const nombreDe = (id: string) => cards.find((c) => c.source === id)?.displayName ?? id;
  const campo =
    "w-full rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-sm transition-colors focus:border-accent";

  return (
    <section className="rounded-card border border-border bg-surface p-5">
      <h3 className="text-sm font-semibold">{t.sources.scanTitle}</h3>
      <p className="mb-3 mt-0.5 text-xs text-ink-soft">{t.sources.scanHint}</p>

      <form onSubmit={lanzar} className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs text-ink-soft">
          {t.sources.profileName}
          <input value={nombre} onChange={(e) => setNombre(e.target.value)} className={campo} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-ink-soft">
          {t.sources.windowDays}
          <input
            type="number"
            min={1}
            max={3650}
            value={ventana}
            onChange={(e) => setVentana(Number(e.target.value))}
            className={campo}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-ink-soft sm:col-span-2">
          {t.sources.keywords}
          <input
            value={tema}
            onChange={(e) => setTema(e.target.value)}
            disabled={descubrimiento}
            className={campo}
          />
        </label>
        <label className="flex items-center gap-2 text-xs text-ink-soft sm:col-span-2">
          <input
            type="checkbox"
            checked={descubrimiento}
            onChange={(e) => setDescubrimiento(e.target.checked)}
          />
          {t.sources.discovery}
        </label>
        <fieldset className="flex items-center gap-3 text-xs text-ink-soft">
          <legend className="mb-1">{t.sources.languages}</legend>
          {IDIOMAS.map((idioma) => (
            <label key={idioma} className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={idiomas.includes(idioma)}
                onChange={(e) =>
                  setIdiomas(
                    e.target.checked ? [...idiomas, idioma] : idiomas.filter((i) => i !== idioma),
                  )
                }
              />
              {idioma}
            </label>
          ))}
        </fieldset>
        <div className="flex items-end justify-end gap-2">
          {scan.status === "running" && scan.scanId && (
            <button
              type="button"
              onClick={() => scan.scanId && cancelar.mutate(scan.scanId)}
              disabled={cancelar.isPending}
              className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs transition-colors hover:bg-surface-2 disabled:opacity-50"
            >
              <Square className="size-3.5" aria-hidden="true" />
              {cancelar.isPending ? t.sources.cancelling : t.sources.cancel}
            </button>
          )}
          <button
            type="submit"
            disabled={!valido || enCurso}
            className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-on-accent transition-colors hover:bg-accent-hover disabled:opacity-50"
          >
            <Play className="size-3.5" aria-hidden="true" />
            {enCurso ? t.sources.scanning : t.sources.scan}
          </button>
        </div>
        {!valido && (nombre !== "" || tema !== "") && (
          <p className="text-xs text-warn sm:col-span-2">{t.sources.profileInvalid}</p>
        )}
      </form>

      {cancelar.isError && (
        <div className="mt-4">
          <ErrorNotice {...comoError(cancelar.error)} />
        </div>
      )}

      {scan.status === "error" && scan.error && (
        <div className="mt-4">
          <ErrorNotice code={scan.error.code} detail={scan.error.detail} />
        </div>
      )}

      {scan.sources.length > 0 && (
        <div className="mt-4">
          <h4 className="mb-2 text-xs font-semibold">{t.sources.progressTitle}</h4>
          <ul className="flex flex-col gap-2">
            {scan.sources.map((id) => {
              const s = scan.perSource[id];
              if (!s) return null;
              return (
                <li key={id} className="rounded-lg border border-border p-2.5 text-xs">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium">{nombreDe(id)}</span>
                    <span className="text-ink-soft">
                      {lineaDeFuente(t, s)}
                      {s.requests > 0 && ` · ${t.sources.requests.replace("{n}", String(s.requests))}`}
                    </span>
                  </div>
                  {s.status === "failed" && s.errorCode && (
                    <div className="mt-2">
                      <ErrorNotice code={s.errorCode} detail={s.detail ?? ""} />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {scan.final && (
        <div className="mt-4 flex flex-col gap-2 text-xs text-ink-soft">
          {scan.final.cancelled && <p className="text-warn">{t.sources.scanCancelled}</p>}
          <p>
            {t.sources.summary
              .replace("{fetched}", String(scan.final.fetched))
              .replace("{canonical}", String(scan.final.canonical))
              .replace("{duplicates}", String(scan.final.duplicates))}
          </p>
          {scan.final.persisted && scan.final.runId && (
            <p>{t.sources.persisted.replace("{runId}", scan.final.runId)}</p>
          )}
          {!scan.final.persisted && !scan.final.persistError && <p>{t.sources.notPersisted}</p>}
          {scan.final.persistError && (
            <ErrorNotice
              code="database"
              detail={scan.final.persistError}
              title={t.sources.persistFailed}
            />
          )}
        </div>
      )}
    </section>
  );
}
