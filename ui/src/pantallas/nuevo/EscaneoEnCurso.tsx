import { AlertTriangle, CheckCircle2, Clock, PauseCircle, XCircle } from "lucide-react";
import type { ReactNode } from "react";

import { Aviso, BotonSecundario, VerDetalle } from "@/components/comunes/Comunes";
import { estadoDeFuente, faseDelEscaneo, type FaseDelEscaneo, type IconoDeFuente, type TonoDeFuente } from "@/lib/progreso";
import { useCancelScan, useSources } from "@/lib/queries";
import { rellenar } from "@/lib/texto";
import { useAsistenteStore } from "@/stores/asistenteStore";
import { useMultiscanStore } from "@/stores/multiscanStore";
import { useT } from "@/stores/settingsStore";

const ICONOS: Record<IconoDeFuente, typeof Clock> = {
  reloj: Clock,
  hecho: CheckCircle2,
  alerta: AlertTriangle,
  cruz: XCircle,
  pausa: PauseCircle,
};

const COLOR: Record<TonoDeFuente, string> = {
  en_curso: "text-accent",
  bien: "text-ok",
  aviso: "text-warn",
  mal: "text-danger",
  neutro: "text-ink-faint",
};

const FASES: FaseDelEscaneo[] = ["buscar", "limpiar", "juez", "resultado"];

/**
 * El escaneo mientras dura: en qué fase va y, fuente a fuente, qué está
 * pasando en palabras de todos los días (lib/progreso.ts). El código técnico
 * de un fallo solo aparece en «Ver detalle».
 */
export function EscaneoEnCurso({ alTerminar }: { alTerminar?: ReactNode }) {
  const t = useT();
  const scan = useMultiscanStore((s) => s.scan);
  const nombre = useAsistenteStore((s) => s.nombre || s.tema);
  const cancelar = useCancelScan();
  const fuentes = useSources();
  const fase = faseDelEscaneo(scan);
  const nombreDe = (id: string) => fuentes.data?.sources.find((c) => c.source === id)?.displayName ?? id;
  const estados = scan.sources.flatMap((id) => (scan.perSource[id] ? [[id, estadoDeFuente(scan.perSource[id])] as const] : []));
  const terminadas = estados.filter(([, e]) => e.tono !== "en_curso").length;
  const encontrados = estados.reduce((total, [, e]) => total + e.items, 0);
  const noUsadas = (fuentes.data?.sources ?? []).filter((c) => !scan.sources.includes(c.source));
  const tecnicos = estados.filter(([, e]) => e.codigo);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-semibold">{rellenar(t.progreso.titulo, { nombre })}</h1>
          <p className="mt-1 text-sm text-ink-soft">{t.progreso.explica}</p>
        </div>
        {scan.status === "running" && scan.scanId && (
          <BotonSecundario onClick={() => scan.scanId && cancelar.mutate(scan.scanId)} disabled={cancelar.isPending}>
            {cancelar.isPending ? t.progreso.cancelando : t.progreso.cancelar}
          </BotonSecundario>
        )}
      </div>

      <ol className="grid gap-2 sm:grid-cols-4" aria-label={t.progreso.fuentes}>
        {FASES.map((f, i) => {
          const aqui = f === fase;
          const hecha = FASES.indexOf(fase) > i;
          return (
            <li
              key={f}
              aria-current={aqui ? "step" : undefined}
              className={`rounded-lg border px-3 py-2.5 text-sm ${
                aqui ? "border-accent bg-accent-soft text-ink" : hecha ? "border-border bg-surface text-ok" : "border-border bg-surface text-ink-faint"
              }`}
            >
              <p className="font-semibold">
                {hecha ? "✓ " : `${i + 1} · `}
                {t.progreso.fase[f]}
              </p>
              <p className="text-[13px]">{t.progreso.faseExplica[f]}</p>
            </li>
          );
        })}
      </ol>

      {fase === "juez" && <Aviso tono="info" titulo={t.progreso.juzgando} />}

      <section className="rounded-card border border-border bg-surface p-5 shadow-card">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-base font-semibold">{t.progreso.fuentes}</h2>
          <p className="text-sm text-ink-soft">
            {rellenar(t.progreso.fuentesListas, { n: terminadas, total: estados.length })}
            {" · "}
            {rellenar(t.progreso.encontrados, { n: encontrados })}
          </p>
        </div>
        <ul className="divide-y divide-border">
          {estados.map(([id, e]) => {
            const Icono = ICONOS[e.icono];
            return (
              <li key={id} data-fuente={id} className="grid grid-cols-[24px_160px_1fr_auto] items-center gap-3 py-3 text-sm">
                <Icono className={`size-5 ${COLOR[e.tono]} ${e.tono === "en_curso" ? "animate-pulse" : ""}`} aria-hidden="true" />
                <span className="font-semibold">{nombreDe(id)}</span>
                <span className="text-ink-soft">
                  <span className={`font-medium ${COLOR[e.tono]}`}>{t.progreso.palabra[e.palabra]}</span>
                  {" · "}
                  {t.progreso.frase[e.frase]}
                </span>
                <span className="font-semibold tabular-nums">{e.items}</span>
              </li>
            );
          })}
          {noUsadas.map((c) => (
            <li key={c.source} className="grid grid-cols-[24px_160px_1fr_auto] items-center gap-3 py-3 text-sm">
              <PauseCircle className="size-5 text-ink-faint" aria-hidden="true" />
              <span className="font-semibold">{c.displayName}</span>
              <span className="text-ink-soft">
                <span className="font-medium text-ink-faint">{t.progreso.palabra.no_se_usa}</span>
                {" · "}
                {t.progreso.noUsada}
              </span>
              <span className="text-ink-faint">—</span>
            </li>
          ))}
        </ul>
      </section>

      {scan.status === "error" && scan.error && (
        <Aviso tono="mal" titulo={t.errors[scan.error.code as keyof typeof t.errors] ?? t.comun.algoFallo} />
      )}

      {(tecnicos.length > 0 || scan.error) && (
        <VerDetalle>
          <ul className="flex flex-col gap-1 font-mono text-[13px] text-ink-soft">
            {tecnicos.map(([id, e]) => (
              <li key={id}>
                {id}: {e.codigo} {scan.perSource[id]?.detail ?? ""}
              </li>
            ))}
            {scan.error && (
              <li>
                {scan.error.code}: {scan.error.detail}
              </li>
            )}
          </ul>
        </VerDetalle>
      )}

      {fase === "resultado" && alTerminar}
    </div>
  );
}
