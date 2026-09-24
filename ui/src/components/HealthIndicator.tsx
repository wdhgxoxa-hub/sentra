import { Database, Cpu } from "lucide-react";

import { ErrorNotice } from "@/components/ErrorNotice";
import { useAppHealth } from "@/lib/queries";
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

  const { postgres, sidecar } = health.data;
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

      {/* Si el motor no arrancó, se dice por qué y cómo arreglarlo (D-D),
          no solo un punto rojo. */}
      {health.data.sidecarLaunch && (
        <ErrorNotice
          code={health.data.sidecarLaunch.code}
          detail={health.data.sidecarLaunch.detail}
        />
      )}
    </div>
  );
}
