import { Plus } from "lucide-react";
import { useState, type ReactNode } from "react";

import { AccionPrincipal, Aviso, BotonSecundario } from "@/components/comunes/Comunes";
import { DossierGuardado } from "@/components/nicho/DocumentosDelNicho";
import { porQueDelNicho, TarjetaDeNicho } from "@/components/nicho/TarjetaDeNicho";
import type { AvisoDelUltimoEscaneo } from "@/lib/radar";
import type { AccionDePaso } from "@/lib/siguientePaso";
import type { Modo, NichoEnPantalla } from "@/modos/tipos";
import { useSettingsStore, useT } from "@/stores/settingsStore";
import type { RunOverview } from "@/types/radar";

import { ResultadoDeUnEscaneo } from "./nuevo/ResultadoDeUnEscaneo";

function fecha(iso: string, idioma: string): string {
  return new Date(iso).toLocaleString(idioma, { dateStyle: "short", timeStyle: "short" });
}

/**
 * Radar (Fase 2): los nichos del último escaneo que encontró alguno. Si el
 * último escaneo no encontró ninguno, un aviso lo dice (con su fecha) y
 * enseña su resultado al pulsar; los nichos de antes no se pierden. Cada
 * nicho lleva a su ficha, con dossier y plan. Genérico (P2).
 */
export function Radar({
  modo,
  nichos,
  descartados,
  escaneo,
  aviso,
  cargando,
  fallo,
  evidencia,
  onNuevo,
  onAbrir,
  onAccion,
}: {
  modo: Modo;
  nichos: NichoEnPantalla[];
  descartados: NichoEnPantalla[];
  escaneo: RunOverview | null;
  aviso: AvisoDelUltimoEscaneo | null;
  cargando: boolean;
  fallo: boolean;
  evidencia: ReactNode;
  onNuevo: () => void;
  onAbrir: (id: string) => void;
  onAccion: (accion: AccionDePaso, nicho?: NichoEnPantalla) => void;
}) {
  const t = useT();
  const idioma = useSettingsStore((s) => s.language);
  const [verUltimo, setVerUltimo] = useState(false);

  return (
    <div className="mx-auto flex max-w-[1080px] flex-col gap-6" data-pantalla="radar">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-semibold">{t.radar.titulo}</h1>
          <p className="mt-1 max-w-[70ch] text-[15px] text-ink-soft">{t.radar.explica}</p>
        </div>
        <AccionPrincipal onClick={onNuevo}>
          <Plus className="size-4" aria-hidden="true" />
          {t.nav.nuevo}
        </AccionPrincipal>
      </header>

      {aviso && (
        <div className="flex flex-col gap-3" data-aviso-ultimo="">
          <Aviso tono="info" titulo={t.radar.avisoUltimo.replace("{name}", aviso.nombre).replace("{date}", fecha(aviso.fecha, idioma))}>
            <p>{t.radar.avisoUltimoExplica}</p>
            <div className="mt-2">
              <BotonSecundario onClick={() => setVerUltimo(!verUltimo)}>
                {verUltimo ? t.radar.ocultarPorQue : t.radar.verPorQue}
              </BotonSecundario>
            </div>
          </Aviso>
          {verUltimo && (
            <ResultadoDeUnEscaneo runId={aviso.runId} cancelado={false} modo={modo} onAccion={onAccion} incrustado />
          )}
        </div>
      )}

      {cargando && <p className="text-sm text-ink-faint">{t.radar.cargando}</p>}
      {fallo && <Aviso tono="mal" titulo={t.radar.error} />}

      {!cargando && !fallo && nichos.length === 0 && (
        <div className="rounded-card border border-dashed border-border-strong p-10 text-center">
          <p className="text-[17px] font-semibold">{t.radar.vacio}</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-ink-soft">{t.radar.vacioExplica}</p>
        </div>
      )}

      {nichos.length > 0 && (
        <section aria-labelledby="nichos" className="flex flex-col gap-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="nichos" className="text-base font-semibold">
              {t.radar.nichos}
            </h2>
            {escaneo && (
              <p className="text-sm text-ink-faint">
                {t.radar.escaneoDel.replace("{name}", escaneo.name).replace("{date}", fecha(escaneo.startedAt, idioma))}
              </p>
            )}
          </div>
          {nichos.map((nicho, i) => (
            <TarjetaDeNicho
              key={nicho.id}
              nicho={nicho}
              modo={modo}
              posicion={i + 1}
              onAbrir={() => onAbrir(nicho.id)}
              extra={<DossierGuardado nicho={nicho} />}
            />
          ))}
        </section>
      )}

      {descartados.length > 0 && (
        <details className="rounded-card border border-border bg-surface p-5 text-sm" data-descartados="">
          <summary className="cursor-pointer select-none font-semibold">
            {t.resultado.descartados.replace("{n}", String(descartados.length))} · {t.resultado.descartadosExplica}
          </summary>
          <ul className="mt-3 divide-y divide-border">
            {descartados.map((d) => (
              <li key={d.id} data-descartado={d.id} className="flex flex-wrap justify-between gap-3 py-2.5">
                <span className="font-medium" data-ajeno="">{d.nombre}</span>
                <span className="text-ink-soft">{porQueDelNicho(t, d)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {evidencia}
    </div>
  );
}
