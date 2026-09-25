import { ArrowRight } from "lucide-react";
import type { ReactNode } from "react";

import type { Modo, NichoEnPantalla } from "@/modos/tipos";
import { useT } from "@/stores/settingsStore";
import type { NicheVerdict } from "@/types/radar";

/** Color del veredicto; siempre va con su palabra (P1: nada solo por color). */
export const COLOR_DEL_VEREDICTO: Record<NicheVerdict, string> = {
  CONSTRUIR: "border-ok/50 bg-ok/10 text-ok",
  "INVESTIGAR MÁS": "border-warn/50 bg-warn/10 text-warn",
  DESCARTAR: "border-border-strong bg-surface-2 text-ink-soft",
};

export function Veredicto({ veredicto }: { veredicto: NicheVerdict }) {
  const t = useT();
  return (
    <span className={`inline-flex h-7 items-center rounded-full border px-3 text-[13px] font-semibold ${COLOR_DEL_VEREDICTO[veredicto]}`}>
      {t.nicho.veredicto[veredicto]}
    </span>
  );
}

/** Por qué el juez decidió eso, en una frase llana. */
export function porQueDelNicho(t: ReturnType<typeof useT>, nicho: NichoEnPantalla): string {
  if (nicho.mezcla) return t.nicho.mezcla;
  return t.nicho.porQue[nicho.porQue as keyof typeof t.nicho.porQue] ?? t.nicho.porQue.otra;
}

/**
 * Un nicho en una lista (resultado del escaneo, Radar). Genérico: el modo dice
 * cómo se leen sus métricas; da igual si es de software o, mañana, de vídeos.
 */
export function TarjetaDeNicho({
  nicho,
  modo,
  posicion,
  onAbrir,
  extra,
}: {
  nicho: NichoEnPantalla;
  modo: Modo;
  posicion?: number;
  onAbrir?: () => void;
  extra?: ReactNode;
}) {
  const t = useT();
  return (
    <article data-nicho={nicho.id} className="flex gap-4 rounded-card border border-border bg-surface p-5 shadow-card">
      {posicion !== undefined && (
        <span className="grid size-11 shrink-0 place-items-center rounded-lg bg-accent-soft text-lg font-bold text-ink">
          {posicion}
        </span>
      )}
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-[17px] font-semibold">{nicho.nombre}</h3>
          <Veredicto veredicto={nicho.veredicto} />
        </div>
        {nicho.subnombre && <p className="text-sm text-ink-soft">{nicho.subnombre}</p>}
        <p className="text-sm text-ink-faint">
          {nicho.metricas.map((m) => modo.metrica(t, m)).join(" · ")}
        </p>
        <p className="text-sm">{porQueDelNicho(t, nicho)}</p>
        {extra}
      </div>
      {onAbrir && (
        <button
          type="button"
          onClick={onAbrir}
          className="inline-flex h-9 shrink-0 items-center gap-1.5 self-start rounded-lg border border-border-strong bg-surface-2 px-4 text-sm font-medium hover:bg-surface"
        >
          {t.nicho.verNicho}
          <ArrowRight className="size-4" aria-hidden="true" />
        </button>
      )}
    </article>
  );
}
