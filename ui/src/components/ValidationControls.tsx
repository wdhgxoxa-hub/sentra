import { useEffect, useState } from "react";

import { useUpdateOpportunityStatus } from "@/lib/queries";
import {
  VALIDATION_FLOW,
  VALIDATION_LABELS,
  type OpportunityCluster,
} from "@/types/radar";

/**
 * Controles de validación humana de una oportunidad.
 *
 * Las notas se editan en local y se guardan al pulsar, no en cada tecla: un
 * análisis comercial se escribe en párrafos, y persistir cada pulsación
 * llenaría la tabla de versiones a medio redactar.
 */
export function ValidationControls({ cluster }: { cluster: OpportunityCluster }) {
  const mutation = useUpdateOpportunityStatus();
  const [notes, setNotes] = useState(cluster.validationNotes ?? "");

  // Al cambiar de oportunidad, el cuadro debe mostrar SUS notas.
  useEffect(() => {
    setNotes(cluster.validationNotes ?? "");
  }, [cluster.clusterKey, cluster.validationNotes]);

  const guardar = (status: (typeof VALIDATION_FLOW)[number]) =>
    mutation.mutate({
      clusterKey: cluster.clusterKey,
      status,
      notes: notes.trim() || null,
    });

  const sucio = notes.trim() !== (cluster.validationNotes ?? "").trim();

  return (
    <section aria-labelledby="validacion" className="flex flex-col gap-3">
      <h3 id="validacion" className="text-sm font-semibold">
        Validación
      </h3>

      <div
        className="flex flex-wrap gap-1"
        role="group"
        aria-label="Estado de validación"
      >
        {VALIDATION_FLOW.map((status) => {
          const activo = cluster.validationStatus === status;
          return (
            <button
              key={status}
              type="button"
              aria-pressed={activo}
              disabled={mutation.isPending}
              onClick={() => guardar(status)}
              className={
                activo
                  ? "rounded-md bg-[--color-ink] px-3 py-1 text-sm text-[--color-surface]"
                  : "rounded-md border border-[--color-border-subtle] px-3 py-1 text-sm hover:bg-[--color-surface-raised] disabled:opacity-50"
              }
            >
              {VALIDATION_LABELS[status]}
            </button>
          );
        })}
      </div>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-[--color-ink-muted]">
          Notas de análisis
        </span>
        <textarea
          value={notes}
          rows={3}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="Qué se construiría, para quién, y por qué ahora"
          className="rounded-md border border-[--color-border-subtle] bg-[--color-surface-raised] px-3 py-2 text-sm"
        />
      </label>

      {sucio && (
        <button
          type="button"
          disabled={mutation.isPending}
          onClick={() => guardar(cluster.validationStatus)}
          className="self-start rounded-md border border-[--color-border-subtle] px-3 py-1 text-sm hover:bg-[--color-surface-raised] disabled:opacity-50"
        >
          Guardar notas
        </button>
      )}

      <p className="text-xs text-[--color-ink-muted]">
        {mutation.isError && (
          <span className="text-[--color-urgency-critical]">
            No se pudo guardar: {String(mutation.error)}
          </span>
        )}
        {!mutation.isError && cluster.validatedAt && (
          <>Decidido el {cluster.validatedAt.slice(0, 16)}</>
        )}
        {!mutation.isError && !cluster.validatedAt && (
          <>Sin decisión registrada todavía</>
        )}
      </p>
    </section>
  );
}
