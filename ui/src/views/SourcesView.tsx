import { ErrorNotice } from "@/components/ErrorNotice";
import { JudgePanel } from "@/components/JudgePanel";
import { MultiscanPanel } from "@/components/MultiscanPanel";
import { SourceCardView } from "@/components/SourceCardView";
import { comoError } from "@/lib/errors";
import { useSetCommercialMode, useSources } from "@/lib/queries";
import { useT } from "@/stores/settingsStore";

/**
 * Sección «Fuentes» (F2): una tarjeta por fuente con su estado verificado,
 * el modo comercial y el escaneo por perfil con progreso por fuente.
 */
export function SourcesView() {
  const t = useT();
  const fuentes = useSources();
  const modoComercial = useSetCommercialMode();
  const lista = fuentes.data?.sources ?? [];

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <header>
        <h2 className="text-base font-semibold">{t.sources.title}</h2>
        <p className="mt-0.5 text-xs text-ink-soft">{t.sources.subtitle}</p>
      </header>

      {fuentes.isPending && <p className="text-sm text-ink-faint">{t.sources.loading}</p>}
      {fuentes.isError && (
        <div className="rounded-card border border-danger/30 bg-surface p-3">
          <ErrorNotice {...comoError(fuentes.error)} title={t.sources.unreachable} />
        </div>
      )}

      {fuentes.data && (
        <>
          <section className="rounded-card border border-border bg-surface p-4">
            <label className="flex items-start gap-3 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                checked={fuentes.data.commercialMode}
                disabled={modoComercial.isPending}
                onChange={(e) => modoComercial.mutate(e.target.checked)}
              />
              <span>
                <span className="font-medium">{t.sources.commercialMode}</span>
                <span className="block text-xs text-ink-soft">{t.sources.commercialModeHint}</span>
              </span>
            </label>
            {modoComercial.isError && (
              <div className="mt-2">
                <ErrorNotice {...comoError(modoComercial.error)} />
              </div>
            )}
          </section>

          {lista.length === 0 ? (
            <p className="text-sm text-ink-faint">{t.sources.empty}</p>
          ) : (
            <div className="grid gap-3">
              {lista.map((card) => (
                <SourceCardView key={card.source} card={card} />
              ))}
            </div>
          )}

          <MultiscanPanel cards={lista} />

          <JudgePanel cards={lista} />
        </>
      )}
    </div>
  );
}
