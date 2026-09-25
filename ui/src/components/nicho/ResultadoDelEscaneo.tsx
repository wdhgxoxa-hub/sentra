import { AccionPrincipal, Aviso, BotonSecundario } from "@/components/comunes/Comunes";
import { tonoDelCaso } from "@/lib/resultado";
import type { AccionDePaso, SiguientePaso } from "@/lib/siguientePaso";
import type { Modo, NichoEnPantalla } from "@/modos/tipos";
import { useT } from "@/stores/settingsStore";

import { porQueDelNicho, TarjetaDeNicho } from "./TarjetaDeNicho";

/**
 * El final de un escaneo en lenguaje llano (P1): qué pasó, qué significa y
 * qué hacer ahora, con una sola acción principal (la del primer paso que
 * lleve a algún sitio). Genérico (P2): nichos ya adaptados y el modo.
 */
export function ResultadoDelEscaneo({
  siguiente,
  nichos,
  descartados,
  modo,
  onAccion,
  incrustado = false,
}: {
  siguiente: SiguientePaso;
  nichos: NichoEnPantalla[];
  descartados: NichoEnPantalla[];
  modo: Modo;
  onAccion: (accion: AccionDePaso, nicho?: NichoEnPantalla) => void;
  /** Dentro de otra pantalla (el Radar): su acción principal ya es otra. */
  incrustado?: boolean;
}) {
  const t = useT();
  const { caso, pasos, cifras } = siguiente;
  // Dentro del Radar, «Ir al Radar» no lleva a ningún sitio nuevo.
  const util = (a: AccionDePaso | null): a is AccionDePaso => a !== null && !(incrustado && a === "abrir_radar");
  const principal = pasos.map((p) => p.accion).find(util) ?? null;
  const otras = [...new Set(pasos.map((p) => p.accion).filter((a): a is AccionDePaso => util(a) && a !== principal))];

  return (
    <section data-resultado={caso} className="flex flex-col gap-5">
      <Aviso tono={tonoDelCaso(caso)} titulo={t.resultado.titulo[caso]}>
        {t.resultado.significa[caso]}
      </Aviso>

      {cifras ? (
        <dl className="grid gap-3 sm:grid-cols-3">
          {(
            [
              [t.resultado.cifras.leidas, cifras.leidas],
              [t.resultado.cifras.conDolor, cifras.conDolor],
              [t.resultado.cifras.personas, cifras.personasNecesarias],
            ] as const
          ).map(([etiqueta, valor]) => (
            <div key={etiqueta} className="rounded-card border border-border bg-surface p-4 shadow-card">
              <dt className="text-sm text-ink-soft">{etiqueta}</dt>
              <dd className="text-[28px] font-bold tabular-nums">{valor}</dd>
            </div>
          ))}
        </dl>
      ) : (
        siguiente.sinDetalle && caso === "cero_nichos" && <p className="text-sm text-ink-faint">{t.resultado.sinDetalle}</p>
      )}

      {nichos.map((nicho, i) => (
        <TarjetaDeNicho key={nicho.id} nicho={nicho} modo={modo} posicion={i + 1} onAbrir={() => onAccion("abrir_nicho", nicho)} />
      ))}

      <section className="flex flex-col gap-4 rounded-card border border-border bg-surface p-6 shadow-card">
        <h2 className="text-base font-semibold">{t.resultado.queHacer}</h2>
        <ol className="flex list-decimal flex-col gap-2 pl-5 text-[15px]">
          {pasos.map((p) => (
            <li key={p.clave}>{t.resultado.paso[p.clave]}</li>
          ))}
        </ol>
        <div className="flex flex-wrap items-center justify-end gap-3">
          {otras.map((accion) => (
            <BotonSecundario key={accion} onClick={() => onAccion(accion, nichos[0])}>
              {t.resultado.accion[accion]}
            </BotonSecundario>
          ))}
          {principal &&
            (incrustado ? (
              <BotonSecundario onClick={() => onAccion(principal, nichos[0])}>{t.resultado.accion[principal]}</BotonSecundario>
            ) : (
              <AccionPrincipal onClick={() => onAccion(principal, nichos[0])}>{t.resultado.accion[principal]}</AccionPrincipal>
            ))}
        </div>
      </section>

      {descartados.length > 0 && (
        <details className="rounded-card border border-border bg-surface p-5 text-sm">
          <summary className="cursor-pointer select-none font-semibold">
            {t.resultado.descartados.replace("{n}", String(descartados.length))} · {t.resultado.descartadosExplica}
          </summary>
          <ul className="mt-3 divide-y divide-border">
            {descartados.map((d) => (
              <li key={d.id} className="flex flex-wrap justify-between gap-3 py-2.5">
                <span className="font-medium">{d.nombre}</span>
                <span className="text-ink-soft">{porQueDelNicho(t, d)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
