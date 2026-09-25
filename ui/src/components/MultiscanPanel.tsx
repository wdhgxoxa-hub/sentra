import { Gauge, Play, Square } from "lucide-react";
import { useState } from "react";

import { ErrorNotice } from "@/components/ErrorNotice";
import { comoError } from "@/lib/errors";
import { cifrasDeLaEstimacion, sePuedeConfirmar } from "@/lib/estimacion";
import { useCancelScan, useEstimateScan, useTriggerMultiscan } from "@/lib/queries";
import { useMultiscanStore } from "@/stores/multiscanStore";
import { useSettingsStore, useT } from "@/stores/settingsStore";
import type { ScanEstimate, ScanProfileInput, SourceCard, SourceScanSummary } from "@/types/radar";

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
  const estimar = useEstimateScan();
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
  // Fase 1, B4: el perfil estimado espera confirmación; se escanea ese, no lo
  // que haya en el formulario al confirmar (la confirmación es de ese perfil).
  const [pendiente, setPendiente] = useState<{ perfil: ScanProfileInput; estimacion: ScanEstimate } | null>(null);

  const palabras = tema.split(",").map((p) => p.trim()).filter(Boolean);
  // Las mismas reglas que valida el motor (ScanProfile): tema o descubrimiento.
  const valido =
    nombre.trim() !== "" &&
    idiomas.length > 0 &&
    ventana >= 1 &&
    descubrimiento !== palabras.length > 0;
  const enCurso = estimar.isPending || escanear.isPending || scan.status === "running";

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
    // Primero la estimación: sin confirmarla, el motor no escanea.
    setPendiente(null);
    estimar.mutate(perfil, { onSuccess: (estimacion) => setPendiente({ perfil, estimacion }) });
  };

  const confirmar = () => {
    if (!pendiente) return;
    const { perfil, estimacion } = pendiente;
    setPendiente(null);
    reset();
    escanear.mutate(
      { profile: perfil, confirmation: estimacion.confirmationId },
      { onError: (error) => fail(comoError(error)) },
    );
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
            {estimar.isPending ? t.sources.estimating : enCurso ? t.sources.scanning : t.sources.scan}
          </button>
        </div>
        {!valido && (nombre !== "" || tema !== "") && (
          <p className="text-xs text-warn sm:col-span-2">{t.sources.profileInvalid}</p>
        )}
      </form>

      {estimar.isError && (
        <div className="mt-4">
          <ErrorNotice {...comoError(estimar.error)} />
        </div>
      )}

      {pendiente && (
        <ConfirmacionDeEscaneo
          estimacion={pendiente.estimacion}
          onConfirmar={confirmar}
          onCancelar={() => setPendiente(null)}
        />
      )}

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

/**
 * Antes de escanear (Fase 1, B4): llamadas y tokens estimados de Gemini, lo
 * gastado hoy y lo que queda. Solo «Confirmar y escanear» escanea; sin
 * presupuesto hoy no hay botón y el texto dice dónde subirlo.
 */
function ConfirmacionDeEscaneo({
  estimacion,
  onConfirmar,
  onCancelar,
}: {
  estimacion: ScanEstimate;
  onConfirmar: () => void;
  onCancelar: () => void;
}) {
  const t = useT();
  const idioma = useSettingsStore((s) => s.language);
  const e = estimacion.estimate;
  const c = cifrasDeLaEstimacion(e, idioma);
  const puede = sePuedeConfirmar(e);
  return (
    <div
      role="dialog"
      aria-labelledby="confirmar-escaneo"
      className="mt-4 flex flex-col gap-2 rounded-lg border border-accent/40 bg-accent-soft/40 p-4 text-xs"
    >
      <h4 id="confirmar-escaneo" className="flex items-center gap-2 text-sm font-semibold">
        <Gauge className="size-4" aria-hidden="true" />
        {t.sources.confirmTitle}
      </h4>
      <p className="text-ink-soft">{t.sources.confirmEstimated}</p>
      <ul className="flex flex-col gap-1">
        <li>{t.sources.confirmCalls.replace("{calls}", c.llamadas)}</li>
        <li>{t.sources.confirmTokens.replace("{tokens}", c.tokens)}</li>
        <li>{t.sources.confirmSpent.replace("{calls}", c.gastadoLlamadas).replace("{tokens}", c.gastadoTokens)}</li>
        <li>{t.sources.confirmLeft.replace("{calls}", c.quedaLlamadas).replace("{tokens}", c.quedaTokens)}</li>
      </ul>
      <p className="text-ink-soft">{e.withHistory ? t.sources.confirmWithHistory : t.sources.confirmNoHistory}</p>
      {!puede && <p className="text-warn">{t.sources.confirmNoBudget}</p>}
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancelar}
          className="rounded-lg border border-border px-3 py-1.5 text-xs transition-colors hover:bg-surface-2"
        >
          {t.sources.confirmCancel}
        </button>
        {puede && (
          <button
            type="button"
            onClick={onConfirmar}
            className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-on-accent transition-colors hover:bg-accent-hover"
          >
            <Play className="size-3.5" aria-hidden="true" />
            {t.sources.confirmScan}
          </button>
        )}
      </div>
    </div>
  );
}
