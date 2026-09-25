/**
 * Piezas comunes de las pantallas de la Fase 2 (P1: facilidad de uso)
 * ===================================================================
 *
 * - `AccionPrincipal`: la acción grande y evidente de una pantalla (una sola;
 *   el humo la cuenta por `data-accion-principal`).
 * - `VerDetalle`: el único sitio donde puede ir lo técnico, plegado.
 * - `Aviso`: un mensaje con icono y palabra, nunca solo color.
 * - `Pasos`: dónde está la persona en el asistente.
 */

import { AlertTriangle, Check, CircleX, Info } from "lucide-react";
import type { ReactNode } from "react";

import { useT } from "@/stores/settingsStore";

export function AccionPrincipal({
  children,
  onClick,
  disabled = false,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      data-accion-principal=""
      onClick={onClick}
      disabled={disabled}
      className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-accent px-6 text-[15px] font-semibold text-on-accent shadow-card transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-45"
    >
      {children}
    </button>
  );
}

export function BotonSecundario({
  children,
  onClick,
  disabled = false,
  etiqueta,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  etiqueta?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={etiqueta}
      className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-border-strong bg-surface-2 px-4 text-sm font-medium text-ink transition-colors hover:bg-surface disabled:cursor-not-allowed disabled:opacity-45"
    >
      {children}
    </button>
  );
}

export function VerDetalle({ children }: { children: ReactNode }) {
  const t = useT();
  return (
    <details className="group rounded-lg border border-border bg-surface px-4 py-3 text-sm">
      <summary className="cursor-pointer select-none font-medium text-ink-soft group-open:mb-3">
        {t.comun.verDetalle}
      </summary>
      {children}
    </details>
  );
}

export type TonoDeAviso = "bien" | "aviso" | "mal" | "info";

const ESTILO: Record<TonoDeAviso, { caja: string; icono: string; Icono: typeof Info }> = {
  bien: { caja: "border-ok/40 bg-ok/10", icono: "text-ok", Icono: Check },
  aviso: { caja: "border-warn/40 bg-warn/10", icono: "text-warn", Icono: AlertTriangle },
  mal: { caja: "border-danger/40 bg-danger/10", icono: "text-danger", Icono: CircleX },
  info: { caja: "border-accent/40 bg-accent-soft", icono: "text-accent", Icono: Info },
};

export function Aviso({ tono, titulo, children }: { tono: TonoDeAviso; titulo: string; children?: ReactNode }) {
  const { caja, icono, Icono } = ESTILO[tono];
  return (
    <div role={tono === "mal" ? "alert" : "status"} className={`flex gap-3 rounded-lg border p-4 ${caja}`}>
      <Icono className={`mt-0.5 size-5 shrink-0 ${icono}`} aria-hidden="true" />
      <div className="flex flex-col gap-1 text-sm">
        <p className="font-semibold text-ink">{titulo}</p>
        {children && <div className="text-ink-soft">{children}</div>}
      </div>
    </div>
  );
}

export function Pasos({ nombres, actual }: { nombres: string[]; actual: number }) {
  return (
    <ol className="grid gap-2 sm:grid-cols-3" aria-label={nombres.join(" · ")}>
      {nombres.map((nombre, i) => {
        const numero = i + 1;
        const hecho = numero < actual;
        const aqui = numero === actual;
        return (
          <li
            key={nombre}
            aria-current={aqui ? "step" : undefined}
            className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 text-sm font-medium ${
              aqui ? "border-accent bg-surface text-ink" : hecho ? "border-border bg-surface text-ok" : "border-border bg-surface text-ink-faint"
            }`}
          >
            <span
              className={`grid size-6 shrink-0 place-items-center rounded-full border text-[13px] ${
                aqui ? "border-accent bg-accent text-on-accent" : "border-current"
              }`}
              aria-hidden="true"
            >
              {hecho ? <Check className="size-3.5" /> : numero}
            </span>
            {nombre}
          </li>
        );
      })}
    </ol>
  );
}
