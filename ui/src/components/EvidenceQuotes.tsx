import { Languages, Loader2, Quote as QuoteIcon } from "lucide-react";
import { useState } from "react";

import { ErrorNotice } from "@/components/ErrorNotice";
import { comoError, type AppError } from "@/lib/errors";
import { ipc } from "@/lib/ipc";
import { useSettingsStore, useT } from "@/stores/settingsStore";
import type { EvidenceQuote, QuoteTranslation } from "@/types/radar";

/**
 * Citas textuales de la oportunidad, con traducción a un clic.
 *
 * Las quejas vienen casi siempre en inglés y son la prueba sobre la que se
 * decide si construir algo: leerlas deprisa importa.
 *
 * Lo traducido se guarda mientras dure la vista, así que alternar entre
 * original y traducción no vuelve a pedir nada ni parpadea. La clave de
 * caché lleva el idioma, de modo que cambiar de idioma pide la traducción
 * nueva en lugar de servir la anterior.
 */
export function EvidenceQuotes({ quotes }: { quotes: EvidenceQuote[] }) {
  const t = useT();
  const language = useSettingsStore((state) => state.language);

  const [traducido, setTraducido] = useState(false);
  const [cache, setCache] = useState<Record<string, QuoteTranslation>>({});
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<AppError | null>(null);

  const clave = (texto: string) => `${language}|${texto}`;

  const alternar = async () => {
    if (traducido) {
      setTraducido(false);
      return;
    }

    const faltan = quotes
      .map((cita) => cita.quote)
      .filter((texto) => !(clave(texto) in cache));

    if (faltan.length === 0) {
      setTraducido(true);
      return;
    }

    setCargando(true);
    setError(null);
    try {
      const traducciones = await ipc.translateQuotes(faltan, language);
      setCache((previo) => {
        const siguiente = { ...previo };
        faltan.forEach((texto, indice) => {
          const traduccion = traducciones[indice];
          if (traduccion) siguiente[clave(texto)] = traduccion;
        });
        return siguiente;
      });
      setTraducido(true);
    } catch (fallo) {
      setError(comoError(fallo));
    } finally {
      setCargando(false);
    }
  };

  // Si nada de lo traducido es fiable del todo, se dice una vez arriba en
  // lugar de repetir el aviso en cada tarjeta.
  const hayAproximadas =
    traducido &&
    quotes.some((cita) => cache[clave(cita.quote)]?.approximate === true);

  return (
    <section>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold">
          <QuoteIcon className="size-4 text-ink-soft" aria-hidden="true" />
          {t.quotes.title}
          <span className="text-xs font-normal text-ink-faint">
            ({quotes.length} {t.quotes.count})
          </span>
        </h3>

        <button
          type="button"
          onClick={alternar}
          disabled={cargando}
          aria-pressed={traducido}
          className={`ml-auto inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-50 ${
            traducido
              ? "border-accent bg-accent-soft text-accent"
              : "border-border text-ink-soft hover:bg-surface-2 hover:text-ink"
          }`}
        >
          {cargando ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <Languages className="size-3.5" aria-hidden="true" />
          )}
          {cargando
            ? t.quotes.translating
            : traducido
              ? t.quotes.showOriginal
              : t.quotes.translate}
        </button>
      </div>

      {error && (
        <div className="mb-2">
          <ErrorNotice {...error} title={t.quotes.error} />
        </div>
      )}

      {hayAproximadas && (
        <p className="mb-2 text-[11px] leading-relaxed text-warn">
          {t.quotes.approximate} {t.quotes.offlineHint}
        </p>
      )}

      <ul className="flex flex-col gap-2">
        {quotes.map((cita) => {
          const traduccion = cache[clave(cita.quote)];
          const mostrada = traducido && traduccion ? traduccion.text : cita.quote;

          return (
            <li
              key={cita.signalId}
              className="rounded-card border-l-2 border-accent bg-surface py-2 pl-3 pr-3"
            >
              <p className="whitespace-pre-line text-sm italic leading-relaxed">
                {mostrada}
              </p>
              <p className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-ink-faint">
                <span className="font-mono">r/{cita.subreddit}</span>
                <span aria-hidden="true">·</span>
                {/* R9: el autor se guarda solo como hash, que sirve para contar
                    autores distintos, no para mostrarlo. */}
                <span>{t.quotes.anonymousAuthor}</span>
                {traducido && traduccion?.approximate && (
                  <>
                    <span aria-hidden="true">·</span>
                    <span className="text-warn">{t.quotes.approximateShort}</span>
                  </>
                )}
              </p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
