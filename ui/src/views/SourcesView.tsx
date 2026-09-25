import { CheckCircle2, CircleX, PauseCircle, TriangleAlert } from "lucide-react";

import { Aviso, VerDetalle } from "@/components/comunes/Comunes";
import { ErrorNotice } from "@/components/ErrorNotice";
import { SourceCardView } from "@/components/SourceCardView";
import { comoError } from "@/lib/errors";
import { estadoDeLaFila, type TonoDeFila } from "@/lib/fuentes";
import { useSetCommercialMode, useSetSourceEnabled, useSources } from "@/lib/queries";
import { useSettingsStore, useT } from "@/stores/settingsStore";
import type { SourceCard } from "@/types/radar";

const ICONO: Record<TonoDeFila, typeof CheckCircle2> = {
  bien: CheckCircle2,
  aviso: TriangleAlert,
  mal: CircleX,
  neutro: PauseCircle,
};
const COLOR: Record<TonoDeFila, string> = {
  bien: "text-ok",
  aviso: "text-warn",
  mal: "text-danger",
  neutro: "text-ink-faint",
};

function Interruptor({ activo, onCambiar, etiqueta, ocupado }: {
  activo: boolean;
  onCambiar: () => void;
  etiqueta: string;
  ocupado: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={activo}
      aria-label={etiqueta}
      title={etiqueta}
      onClick={onCambiar}
      disabled={ocupado}
      className={`relative h-6 w-11 shrink-0 rounded-full border transition-colors disabled:opacity-50 ${
        activo ? "border-transparent bg-accent" : "border-border-strong bg-surface-2"
      }`}
    >
      <span
        className={`absolute top-0.5 size-4.5 rounded-full transition-all ${activo ? "left-[22px] bg-on-accent" : "left-0.5 bg-ink-faint"}`}
      />
    </button>
  );
}

function FilaDeFuente({ card }: { card: SourceCard }) {
  const t = useT();
  const idioma = useSettingsStore((s) => s.language);
  const encender = useSetSourceEnabled();
  const { clave, tono } = estadoDeLaFila(card);
  const Icono = ICONO[tono];
  return (
    <li data-fuente-fila={card.source} className="flex flex-col gap-3 py-4">
      <div className="grid grid-cols-[1fr_auto] items-center gap-4 sm:grid-cols-[200px_1fr_170px_auto]">
        <div className="flex flex-col">
          <span className="text-[15px] font-semibold">{card.displayName}</span>
          {!card.commercialUseAllowed && <span className="text-[13px] text-ink-faint">{t.sources.personalOnly}</span>}
        </div>
        <div className="flex items-start gap-2 text-sm">
          <Icono className={`mt-0.5 size-4 shrink-0 ${COLOR[tono]}`} aria-hidden="true" />
          <span>
            <span className={`font-semibold ${COLOR[tono]}`}>{t.sources.fila[clave]}</span>
            <span className="block text-ink-soft">{t.sources.filaExplica[clave]}</span>
          </span>
        </div>
        <span className="hidden text-sm text-ink-soft sm:block">
          {card.lastVerifiedAt
            ? new Date(card.lastVerifiedAt).toLocaleString(idioma, { dateStyle: "short", timeStyle: "short" })
            : t.sources.nunca}
        </span>
        <Interruptor
          activo={!card.disabled}
          ocupado={encender.isPending}
          etiqueta={`${card.disabled ? t.sources.enable : t.sources.disable} ${card.displayName}`}
          onCambiar={() => encender.mutate({ source: card.source, enabled: card.disabled })}
        />
      </div>
      {encender.isError && <ErrorNotice {...comoError(encender.error)} />}
      <VerDetalle>
        <SourceCardView card={card} />
      </VerDetalle>
    </li>
  );
}

/**
 * Fuentes (Fase 2): una fila por fuente que dice en palabras si entra en los
 * escaneos, su última respuesta real y un interruptor. La cuenta, las claves,
 * el coste y los términos van en «Ver detalle». Compartida por todos los
 * modos (P2). El escaneo ya no vive aquí: está en «Nuevo escaneo».
 */
export function SourcesView() {
  const t = useT();
  const fuentes = useSources();
  const modoComercial = useSetCommercialMode();
  const lista = fuentes.data?.sources ?? [];

  return (
    <div className="mx-auto flex max-w-[1080px] flex-col gap-6" data-pantalla="fuentes">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-semibold">{t.sources.title}</h1>
          <p className="mt-1 max-w-[70ch] text-[15px] text-ink-soft">{t.sources.subtitle}</p>
        </div>
        {fuentes.data && (
          <label className="flex items-center gap-3 text-sm">
            <Interruptor
              activo={fuentes.data.commercialMode}
              ocupado={modoComercial.isPending}
              etiqueta={t.sources.commercialMode}
              onCambiar={() => modoComercial.mutate(!fuentes.data.commercialMode)}
            />
            <span>
              <span className="font-semibold">{t.sources.commercialMode}</span>
              <span className="block max-w-xs text-[13px] text-ink-soft">{t.sources.commercialModeHint}</span>
            </span>
          </label>
        )}
      </header>

      {fuentes.isPending && <p className="text-sm text-ink-faint">{t.sources.loading}</p>}
      {fuentes.isError && <Aviso tono="mal" titulo={t.sources.unreachable} />}
      {modoComercial.isError && <ErrorNotice {...comoError(modoComercial.error)} />}

      {fuentes.data &&
        (lista.length === 0 ? (
          <p className="text-sm text-ink-faint">{t.sources.empty}</p>
        ) : (
          <section className="rounded-card border border-border bg-surface px-5 shadow-card">
            <div className="hidden grid-cols-[200px_1fr_170px_auto] gap-4 border-b border-border py-3 text-[13px] font-semibold text-ink-faint sm:grid">
              <span>{t.sources.columnas.fuente}</span>
              <span>{t.sources.columnas.estado}</span>
              <span>{t.sources.columnas.ultima}</span>
              <span>{t.sources.columnas.activa}</span>
            </div>
            <ul className="divide-y divide-border">
              {lista.map((card) => (
                <FilaDeFuente key={card.source} card={card} />
              ))}
            </ul>
          </section>
        ))}
    </div>
  );
}
