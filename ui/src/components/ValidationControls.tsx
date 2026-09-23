import { useEffect, useState } from "react";

import { ErrorNotice } from "@/components/ErrorNotice";
import { comoError } from "@/lib/errors";
import { useUpdateOpportunityStatus } from "@/lib/queries";
import { useT } from "@/stores/settingsStore";
import {
  VALIDATION_FLOW,
  type OpportunityCluster,
  type ValidationStatus,
} from "@/types/radar";

/**
 * Controles de validación de una oportunidad.
 *
 * Las notas se editan en local y se guardan al pulsar, no en cada tecla: un
 * análisis se escribe en párrafos, y persistir cada pulsación llenaría la
 * tabla de versiones a medio redactar.
 */
export function ValidationControls({ cluster }: { cluster: OpportunityCluster }) {
  const t = useT();
  const mutation = useUpdateOpportunityStatus();
  const [notes, setNotes] = useState(cluster.validationNotes ?? "");

  // Al cambiar de oportunidad, el cuadro debe mostrar SUS notas.
  useEffect(() => {
    setNotes(cluster.validationNotes ?? "");
  }, [cluster.clusterKey, cluster.validationNotes]);

  const guardar = (status: ValidationStatus) =>
    mutation.mutate({
      clusterKey: cluster.clusterKey,
      status,
      notes: notes.trim() || null,
    });

  const sucio = notes.trim() !== (cluster.validationNotes ?? "").trim();

  return (
    <section
      aria-labelledby="validacion"
      className="flex flex-col gap-3 rounded-card border border-border bg-surface p-5"
    >
      <h3 id="validacion" className="text-sm font-semibold">
        {t.detail.validation}
      </h3>

      <div
        className="flex flex-wrap gap-1.5"
        role="group"
        aria-label={t.detail.validation}
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
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
                activo
                  ? "bg-accent text-on-accent"
                  : "border border-border text-ink-soft hover:bg-surface-2 hover:text-ink"
              }`}
            >
              {t.validation[status]}
            </button>
          );
        })}
      </div>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs text-ink-soft">{t.detail.notes}</span>
        <textarea
          value={notes}
          rows={3}
          onChange={(event) => setNotes(event.target.value)}
          placeholder={t.detail.notesPlaceholder}
          className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm transition-colors focus:border-accent"
        />
      </label>

      {sucio && (
        <button
          type="button"
          disabled={mutation.isPending}
          onClick={() => guardar(cluster.validationStatus)}
          className="self-start rounded-lg border border-border px-3 py-1.5 text-xs transition-colors hover:bg-surface-2 disabled:opacity-50"
        >
          {t.detail.saveNotes}
        </button>
      )}

      <p className="text-[11px] text-ink-faint">
        {mutation.isError ? (
          <ErrorNotice {...comoError(mutation.error)} title={t.detail.saveError} />
        ) : cluster.validatedAt ? (
          <>
            {t.detail.decidedOn} {cluster.validatedAt.slice(0, 16)}
          </>
        ) : (
          t.detail.noDecision
        )}
      </p>
    </section>
  );
}
