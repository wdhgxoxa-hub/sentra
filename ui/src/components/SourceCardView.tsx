import { CheckCircle2, KeyRound, Power, RadioTower } from "lucide-react";
import { useState } from "react";

import { ErrorNotice } from "@/components/ErrorNotice";
import { comoError } from "@/lib/errors";
import { useProbeSource, useSaveSourceCredentials, useSetSourceEnabled } from "@/lib/queries";
import { useT } from "@/stores/settingsStore";
import type { SourceCard, SourceStatusName } from "@/types/radar";

const PUNTO: Record<SourceStatusName, string> = {
  verificada: "bg-ok",
  configurada_sin_verificar: "bg-warn",
  error: "bg-danger",
  no_configurada: "bg-ink-faint",
  deshabilitada_por_usuario: "bg-ink-faint",
};

type Acceso = "public" | "publicOptional" | "optionalSaved" | null;

/**
 * Qué decir del acceso de una fuente que no exige credenciales. «Pública, sin
 * credenciales» solo si no admite ninguna: si tiene una opcional guardada,
 * decir lo contrario sería mentir (la interfaz nunca miente).
 */
export function acceso(card: SourceCard): Acceso {
  if (card.requiresCredentials) return null;
  if (card.credentialFields.length === 0) return "public";
  return card.credentialFields.some((c) => c.configured) ? "optionalSaved" : "publicOptional";
}

/** Fecha y hora locales de una marca ISO 8601: la verificación puede ser de otro día. */
function fechaLocal(iso: string): string {
  return new Date(iso).toLocaleString([], { dateStyle: "short", timeStyle: "short" });
}

/**
 * Tarjeta de una fuente: estado verificado, términos, coste, credenciales,
 * «Probar» y encendido. Verde solo con una respuesta real de la API; lo que
 * no se ha comprobado se dice («sin verificar»), no se pinta de verde.
 */
export function SourceCardView({ card }: { card: SourceCard }) {
  const t = useT();
  const probar = useProbeSource();
  const encender = useSetSourceEnabled();
  const guardar = useSaveSourceCredentials();
  const [valores, setValores] = useState<Record<string, string>>({});

  const campo =
    "w-full rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-sm transition-colors focus:border-accent";
  const boton =
    "flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs transition-colors hover:bg-surface-2 disabled:opacity-50";

  const enviar = (event: React.FormEvent) => {
    event.preventDefault();
    const rellenos = Object.fromEntries(
      Object.entries(valores).filter(([, v]) => v.trim() !== ""),
    );
    guardar.mutate(
      { source: card.source, values: rellenos },
      // El secreto no tiene por qué seguir en memoria ni en pantalla.
      { onSuccess: () => setValores({}) },
    );
  };

  const resultado = probar.data;
  const textoAcceso = acceso(card);

  return (
    <article className="rounded-card border border-border bg-surface p-4">
      <header className="flex flex-wrap items-center gap-2">
        <RadioTower className="size-4 text-ink-soft" aria-hidden="true" />
        <h3 className="text-sm font-semibold">{card.displayName}</h3>
        <span className="flex items-center gap-1.5 rounded-full border border-border px-2 py-0.5 text-[11px]">
          <span className={`size-1.5 rounded-full ${PUNTO[card.status]}`} aria-hidden="true" />
          {t.sources.status[card.status]}
        </span>
        {!card.commercialUseAllowed && (
          <span className="rounded-full bg-medium-soft px-2 py-0.5 text-[11px] text-medium-ink">
            {t.sources.personalOnly}
          </span>
        )}
        {card.excludedByCommercialMode && (
          <span className="rounded-full bg-high-soft px-2 py-0.5 text-[11px] text-high-ink">
            {t.sources.excludedByCommercial}
          </span>
        )}
      </header>

      <dl className="mt-2 grid gap-1 text-xs text-ink-soft">
        <div>
          {card.lastVerifiedAt
            ? t.sources.lastVerified.replace("{when}", fechaLocal(card.lastVerifiedAt))
            : t.sources.neverVerified}
        </div>
        <div>
          <dt className="inline font-medium">{t.sources.cost}: </dt>
          <dd className="inline">
            {t.sources.costUnit[card.costUnit]}
            {card.costNote ? ` · ${card.costNote}` : ""}
          </dd>
        </div>
        <div>
          <dt className="inline font-medium">{t.sources.terms}: </dt>
          {/* Texto seleccionable: la ventana no abre enlaces externos. */}
          <dd className="inline select-all break-all">{card.termsUrl}</dd>
        </div>
        {textoAcceso && <div>{t.sources[textoAcceso]}</div>}
      </dl>

      {/* Sin configurar con motivo (p. ej. pendiente de aprobación, R7): se dice por qué. */}
      {card.status === "no_configurada" && card.detail && (
        <p className="mt-2 text-xs text-warn">{card.detail}</p>
      )}

      {card.status === "error" && card.errorCode && (
        <div className="mt-3">
          <ErrorNotice code={card.errorCode} detail={card.detail ?? ""} />
          {/* AUD2-012: el mismo `active` que decide el escaneo. */}
          {!card.active && <p className="mt-1 text-xs text-warn">{t.sources.excludedUntilProbe}</p>}
        </div>
      )}

      {card.credentialFields.length > 0 && (
        <form onSubmit={enviar} className="mt-3 flex flex-col gap-2">
          <p className="flex items-center gap-1.5 text-xs font-medium">
            <KeyRound className="size-3.5" aria-hidden="true" />
            {t.sources.credentials}
          </p>
          {card.credentialFields.map((c) => (
            <label key={c.name} className="flex flex-col gap-1 text-xs text-ink-soft">
              <span>
                {c.name} ·{" "}
                {c.configured ? t.sources.configured : t.sources.notConfigured}
                {!c.required && ` · ${t.sources.optional}`}
              </span>
              <input
                type={c.secret ? "password" : "text"}
                autoComplete="off"
                value={valores[c.name] ?? ""}
                onChange={(e) => setValores({ ...valores, [c.name]: e.target.value })}
                className={campo}
              />
            </label>
          ))}
          <p className="text-[11px] text-ink-faint">{t.sources.secretHint}</p>
          <button
            type="submit"
            disabled={guardar.isPending || Object.values(valores).every((v) => !v.trim())}
            className={`${boton} self-start`}
          >
            {guardar.isPending ? t.sources.saving : t.sources.saveCredentials}
          </button>
          {guardar.isError && <ErrorNotice {...comoError(guardar.error)} />}
        </form>
      )}

      <footer className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => probar.mutate(card.source)}
          disabled={probar.isPending || card.status === "no_configurada"}
          className={boton}
        >
          <CheckCircle2 className="size-3.5" aria-hidden="true" />
          {probar.isPending ? t.sources.probing : t.sources.probe}
        </button>
        <button
          type="button"
          onClick={() => encender.mutate({ source: card.source, enabled: card.disabled })}
          disabled={encender.isPending}
          aria-pressed={!card.disabled}
          className={boton}
        >
          <Power className="size-3.5" aria-hidden="true" />
          {card.disabled ? t.sources.enable : t.sources.disable}
        </button>
      </footer>

      {resultado?.ok && (
        <p className="mt-2 text-xs text-ok">
          {t.sources.probeOk.replace("{detail}", resultado.detail)}
        </p>
      )}
      {resultado && !resultado.ok && resultado.code && (
        <div className="mt-2">
          <ErrorNotice code={resultado.code} detail={resultado.detail} />
        </div>
      )}
      {probar.isError && (
        <div className="mt-2">
          <ErrorNotice {...comoError(probar.error)} />
        </div>
      )}
      {encender.isError && (
        <div className="mt-2">
          <ErrorNotice {...comoError(encender.error)} />
        </div>
      )}
    </article>
  );
}
