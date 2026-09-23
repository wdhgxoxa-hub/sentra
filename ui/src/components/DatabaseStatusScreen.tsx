import { Database, Loader2, RotateCw } from "lucide-react";

import { ErrorNotice } from "@/components/ErrorNotice";
import { comoError } from "@/lib/errors";
import { useRetryDatabase } from "@/lib/queries";
import { useT } from "@/stores/settingsStore";
import type { DatabaseStatus } from "@/types/radar";

/**
 * Pantalla de estado cuando no hay PostgreSQL (D-F).
 *
 * Antes la aplicación se cerraba sin abrir ventana. Ahora arranca, dice por
 * qué no puede leer datos —el motivo traducido y el detalle técnico
 * plegado— y deja reintentar sin reiniciar.
 */
export function DatabaseStatusScreen({ status }: { status: DatabaseStatus }) {
  const t = useT();
  const reintentar = useRetryDatabase();

  return (
    <section
      role="alert"
      className="mx-auto flex max-w-xl flex-col items-start gap-3 rounded-card border border-danger/30 bg-surface p-6"
    >
      <h2 className="flex items-center gap-2 text-base font-semibold text-danger">
        <Database className="size-4" aria-hidden="true" />
        {t.database.title}
      </h2>
      <div className="w-full text-sm">
        <ErrorNotice code={status.code ?? "database_unavailable"} detail={status.detail ?? ""} />
      </div>
      <p className="text-sm leading-relaxed text-ink-soft">{t.database.hint}</p>

      {reintentar.isError && <ErrorNotice {...comoError(reintentar.error)} />}

      <button
        type="button"
        onClick={() => reintentar.mutate()}
        disabled={reintentar.isPending}
        className="inline-flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-on-accent transition-colors hover:bg-accent-hover disabled:opacity-50"
      >
        {reintentar.isPending ? (
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        ) : (
          <RotateCw className="size-4" aria-hidden="true" />
        )}
        {reintentar.isPending ? t.database.retrying : t.common.retry}
      </button>
    </section>
  );
}
