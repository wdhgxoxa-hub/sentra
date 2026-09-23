import { AlertTriangle, ArrowRight, MessageSquare, Trophy, Users } from "lucide-react";

import { SourceBadge } from "@/components/SourceBadge";
import { useTopOpportunities } from "@/lib/queries";
import { useT } from "@/stores/settingsStore";
import { useUiStore } from "@/stores/uiStore";
import type { TopOpportunities } from "@/types/radar";

/**
 * Las mejores oportunidades de la última ejecución (AUD-007).
 *
 * Enseña exactamente lo que entregó el motor: posición, puntuación, menciones
 * y comunidades de cada una, y de dónde salen los datos. Si hay menos de las
 * que se buscaban, lo dice con el motivo; nunca rellena con problemas que no
 * superaron el corte. El objetivo (6) llega del backend, no se repite aquí.
 */
export function TopSix() {
  const t = useT();
  const top = useTopOpportunities();
  const selectClusterKey = useUiStore((state) => state.selectClusterKey);
  const setView = useUiStore((state) => state.setView);

  const abrir = (clusterKey: string) => {
    selectClusterKey(clusterKey);
    setView("opportunity");
  };

  return (
    <section aria-labelledby="top-oportunidades" className="rounded-card border border-border bg-surface p-5">
      <header className="mb-3 flex flex-wrap items-center gap-2">
        <h2 id="top-oportunidades" className="flex items-center gap-2 text-base font-semibold">
          <Trophy className="size-4 text-accent" aria-hidden="true" />
          {top.data ? t.topSix.title.replace("{target}", String(top.data.target)) : t.topSix.titleGeneric}
        </h2>
        {top.data && <Resumen top={top.data} />}
      </header>

      {top.isPending && <p className="text-sm text-ink-faint">{t.topSix.loading}</p>}
      {top.isError && <p className="text-sm text-danger">{t.topSix.error}</p>}
      {top.data === null && (
        <p className="text-sm text-ink-soft">{t.topSix.noRuns}</p>
      )}

      {top.data && top.data.found < top.data.target && (
        <p className="mb-3 flex items-start gap-1.5 rounded-lg bg-warn/10 p-2.5 text-xs text-warn">
          <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden="true" />
          {t.topSix.incomplete
            .replace("{found}", String(top.data.found))
            .replace("{target}", String(top.data.target))}{" "}
          {top.data.reason ? t.topSix.reasons[top.data.reason] : ""}
        </p>
      )}

      {top.data && top.data.items.length > 0 && (
        <ol className="flex flex-col gap-1.5">
          {top.data.items.map((item) => (
            <li
              key={item.clusterKey}
              className="flex items-center gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-surface-2"
            >
              <span className="w-6 shrink-0 text-center font-mono text-sm font-semibold text-accent">
                {item.position}
              </span>
              <span className="min-w-0 flex-1 truncate text-sm font-medium">{item.label}</span>
              <span className="shrink-0 font-mono text-xs tabular-nums">
                {item.finalScore.toFixed(1)} {t.radar.points}
              </span>
              <span className="inline-flex shrink-0 items-center gap-1 text-xs text-ink-soft">
                <MessageSquare className="size-3.5" aria-hidden="true" />
                <span className="font-mono tabular-nums">{item.mentionCount}</span>
                <span className="sr-only">{t.radar.mentions}</span>
              </span>
              <span className="inline-flex shrink-0 items-center gap-1 text-xs text-ink-soft">
                <Users className="size-3.5" aria-hidden="true" />
                <span className="font-mono tabular-nums">{item.communityCount}</span>
                <span className="sr-only">{t.radar.communities}</span>
              </span>
              <button
                type="button"
                onClick={() => abrir(item.clusterKey)}
                aria-label={`${t.topSix.open}: ${item.label}`}
                className="inline-flex shrink-0 items-center rounded-lg p-1 text-accent transition-colors hover:bg-accent-soft"
              >
                <ArrowRight className="size-4" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/** Cuántas se entregaron frente a las buscadas, y de dónde salen los datos. */
function Resumen({ top }: { top: TopOpportunities }) {
  const t = useT();

  return (
    <>
      <span
        className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
          top.complete ? "bg-ok/15 text-ok" : "bg-warn/15 text-warn"
        }`}
      >
        {(top.complete ? t.topSix.complete : t.topSix.partial)
          .replace("{found}", String(top.found))
          .replace("{target}", String(top.target))}
      </span>
      <span className="ml-auto">
        <SourceBadge source={top.dataSource} />
      </span>
    </>
  );
}
