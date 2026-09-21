import { AlertTriangle, Database, Cpu } from "lucide-react";

import { Explain } from "@/components/Explain";
import { useAppHealth, useSettings } from "@/lib/queries";
import { useT } from "@/stores/settingsStore";

/**
 * Estado de las tres piezas.
 *
 * Se informa de cada una por separado porque fallan por separado: la ventana
 * puede estar viva con la base caída, o con la base bien y el motor sin
 * arrancar. Un único punto verde escondería justo lo que hace falta saber
 * para arreglarlo.
 */
export function HealthIndicator() {
  const t = useT();
  const health = useAppHealth();
  const settings = useSettings();

  if (health.isPending) {
    return (
      <p className="px-2 text-xs text-ink-faint">{t.health.checking}</p>
    );
  }

  if (health.isError || !health.data) {
    return (
      <p className="px-2 text-xs text-danger">{t.health.noBackend}</p>
    );
  }

  const { postgres, sidecar, sidecarInfo } = health.data;
  const pieces = [
    { label: t.health.database, state: postgres, Icon: Database },
    { label: t.health.engine, state: sidecar, Icon: Cpu },
  ];

  return (
    <div className="flex flex-col gap-1.5 px-2 text-xs">
      {pieces.map(({ label, state, Icon }) => (
        <div key={label} className="flex items-center gap-2" title={state.detail}>
          <Icon
            className={`size-3.5 shrink-0 ${
              state.ok ? "text-ok" : "text-danger"
            }`}
            aria-hidden="true"
          />
          <span className="flex-1 truncate text-ink-soft">{label}</span>
          <span
            className={`size-1.5 rounded-full ${
              state.ok ? "bg-ok" : "bg-danger"
            }`}
            aria-hidden="true"
          />
          <span className="sr-only">{state.ok ? t.health.up : t.health.down}</span>
        </div>
      ))}

      {settings.data && (
        <p className="pt-0.5 text-[11px] text-ink-faint">
          {settings.data.fetcherMode === "synthetic"
            ? t.health.sourceSynthetic
            : t.health.sourceReddit}
        </p>
      )}

      {/* Mientras el clasificador opere por reglas conviene que se vea: las
          etiquetas de intención valen menos de lo que aparentan. */}
      {sidecarInfo?.nli.engine === "heuristic" && (
        <p className="flex items-center gap-1 text-[11px] text-warn">
          <AlertTriangle className="size-3 shrink-0" aria-hidden="true" />
          {t.health.heuristicNli}
          <Explain
            title={t.health.heuristicNli}
            body={t.health.heuristicNliHint}
            align="start"
          />
        </p>
      )}
    </div>
  );
}
