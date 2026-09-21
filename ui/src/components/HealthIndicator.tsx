import { useAppHealth } from "@/lib/queries";

/**
 * Estado de las tres piezas.
 *
 * Se informa de cada una por separado porque fallan por separado: la
 * ventana puede estar viva con PostgreSQL caido, o con la base bien y el
 * sidecar sin arrancar. Un unico punto verde ocultaria justo lo que hace
 * falta saber para arreglarlo.
 */
export function HealthIndicator() {
  const health = useAppHealth();

  if (health.isPending) {
    return <span className="text-xs text-[--color-ink-muted]">comprobando...</span>;
  }

  if (health.isError || !health.data) {
    return (
      <span className="text-xs text-[--color-urgency-critical]">
        sin respuesta del backend
      </span>
    );
  }

  const { postgres, sidecar, sidecarInfo } = health.data;
  const pieces = [
    { label: "PostgreSQL", state: postgres },
    { label: "Sidecar", state: sidecar },
  ];

  return (
    <div className="flex items-center gap-3 text-xs">
      {pieces.map(({ label, state }) => (
        <span key={label} className="flex items-center gap-1" title={state.detail}>
          <span
            aria-hidden="true"
            className={
              state.ok
                ? "inline-block h-2 w-2 rounded-full bg-[--color-urgency-low]"
                : "inline-block h-2 w-2 rounded-full bg-[--color-urgency-critical]"
            }
          />
          <span className={state.ok ? "text-[--color-ink-muted]" : "font-medium"}>
            {label}
            <span className="sr-only">{state.ok ? ": activo" : ": caido"}</span>
          </span>
        </span>
      ))}

      {/* Mientras el NLI corra en modo heuristico conviene que se vea. */}
      {sidecarInfo?.nli.engine === "heuristic" && (
        <span
          className="rounded bg-[--color-urgency-medium] px-1.5 py-0.5 text-black"
          title="El clasificador zero-shot opera por reglas: transformers no esta instalado"
        >
          NLI heuristico
        </span>
      )}
    </div>
  );
}
