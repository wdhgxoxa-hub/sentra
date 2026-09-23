import { AlertTriangle, Database, Cpu } from "lucide-react";

import { Explain } from "@/components/Explain";
import { useAppHealth } from "@/lib/queries";
import { useT } from "@/stores/settingsStore";
import type { SourceState, SourceStatus } from "@/types/radar";

/** Solo lo verificado contra Reddit es verde. */
const SOURCE_COLORS: Record<SourceState, string> = {
  demo: "bg-warn",
  reddit_sin_credenciales: "bg-danger",
  reddit_sin_verificar: "bg-warn",
  reddit_verificado: "bg-ok",
  reddit_error: "bg-danger",
};

/** Hora local HH:MM de una marca ISO 8601. */
function horaLocal(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function SourceLine({ source }: { source: SourceStatus | null }) {
  const t = useT();

  if (!source) {
    return (
      <p className="flex items-center gap-2 pt-0.5 text-[11px] text-ink-faint">
        <span className="size-1.5 shrink-0 rounded-full bg-ink-faint" aria-hidden="true" />
        {t.health.sourceUnknown}
      </p>
    );
  }

  let evidencia: string | null = null;
  if (source.state === "reddit_verificado" && source.lastSuccessAt) {
    evidencia = t.health.sourceVerifiedAt.replace("{time}", horaLocal(source.lastSuccessAt));
  } else if (source.state === "reddit_error" && source.errorCode) {
    evidencia = t.scanErrors[source.errorCode] ?? null;
  }

  return (
    <div className="pt-0.5 text-[11px]">
      <p className="flex items-center gap-2 text-ink-soft">
        <span
          className={`size-1.5 shrink-0 rounded-full ${SOURCE_COLORS[source.state]}`}
          aria-hidden="true"
        />
        {t.health.sourceStates[source.state]}
      </p>
      {evidencia && <p className="mt-0.5 pl-3.5 text-ink-faint">{evidencia}</p>}
    </div>
  );
}

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

      {/* La fuente se describe por lo que ha pasado de verdad, no por el
          modo elegido (AUD-004): solo un 200 real de Reddit pinta verde. */}
      <SourceLine source={health.data.source} />

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
