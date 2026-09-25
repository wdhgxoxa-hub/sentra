import { ArrowLeft, Play } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { AccionPrincipal, Aviso, BotonSecundario } from "@/components/comunes/Comunes";
import { palabrasDistintas } from "@/lib/cobertura";
import { comoError } from "@/lib/errors";
import { cifrasDeLaEstimacion, sePuedeConfirmar } from "@/lib/estimacion";
import { useEstimateScan, useSources, useTriggerMultiscan } from "@/lib/queries";
import { rellenar } from "@/lib/texto";
import { useAsistenteStore } from "@/stores/asistenteStore";
import { useMultiscanStore } from "@/stores/multiscanStore";
import { useSettingsStore, useT } from "@/stores/settingsStore";
import type { ScanProfileInput } from "@/types/radar";

function Fila({ etiqueta, children }: { etiqueta: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-border py-2.5 text-sm last:border-b-0">
      <dt className="text-ink-soft">{etiqueta}</dt>
      <dd className="text-right font-medium">{children}</dd>
    </div>
  );
}

/**
 * Paso 3: lo que se va a buscar y lo que costará en Gemini. Al entrar se
 * estima (no gasta nada); «Escanear» confirma esa estimación, como exige el
 * motor desde la Fase 1. Cambiar el nombre vuelve a estimar.
 */
export function PasoRevisar() {
  const t = useT();
  const idioma = useSettingsStore((s) => s.language);
  const a = useAsistenteStore();
  const fuentes = useSources();
  const estimar = useEstimateScan();
  const escanear = useTriggerMultiscan();
  const reset = useMultiscanStore((s) => s.reset);
  const fail = useMultiscanStore((s) => s.fail);
  const [nombre, setNombre] = useState(a.nombre);

  const es = a.idiomas.includes("es") ? palabrasDistintas(a.palabras.es) : [];
  const en = a.idiomas.includes("en") ? palabrasDistintas(a.palabras.en) : [];
  const perfil: ScanProfileInput = {
    name: (a.nombre || a.tema || t.nuevoEscaneo.titulo).trim().slice(0, 60),
    keywords: a.sinTema ? [] : [...es, ...en],
    // El idioma de cada palabra es el de su fila: el motor no tiene que adivinarlo.
    keywordLanguages: a.sinTema
      ? {}
      : Object.fromEntries([...es.map((p) => [p, "es"] as const), ...en.map((p) => [p, "en"] as const)]),
    discovery: a.sinTema,
    windowDays: a.dias,
    languages: a.idiomas,
  };
  // Una estimación por perfil distinto (cada una da un identificador nuevo).
  const clave = JSON.stringify(perfil);
  const { mutate: pedirEstimacion } = estimar;
  useEffect(() => {
    pedirEstimacion(JSON.parse(clave) as ScanProfileInput);
  }, [clave, pedirEstimacion]);

  const e = estimar.data?.estimate;
  const c = e ? cifrasDeLaEstimacion(e, idioma) : null;
  const puede = e ? sePuedeConfirmar(e) : false;
  const activas = fuentes.data?.sources.filter((s) => s.active).length;

  const lanzar = () => {
    if (!estimar.data || !puede) return;
    reset();
    a.set({ resultadoSinVer: false });
    escanear.mutate(
      { profile: perfil, confirmation: estimar.data.confirmationId },
      { onError: (error) => fail(comoError(error)) },
    );
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-5 lg:grid-cols-2">
        <section className="rounded-card border border-border bg-surface p-6 shadow-card">
          <h2 className="mb-2 text-base font-semibold">{t.nuevoEscaneo.queSeBusca}</h2>
          <dl>
            <Fila etiqueta={t.nuevoEscaneo.resumen.tema}>{a.sinTema ? t.nuevoEscaneo.sinTema : a.tema}</Fila>
            {!a.sinTema && (
              <Fila etiqueta={t.nuevoEscaneo.resumen.palabras}>
                {rellenar(t.nuevoEscaneo.palabrasPorIdioma, { n: es.length + en.length, es: es.length, en: en.length })}
              </Fila>
            )}
            <Fila etiqueta={t.nuevoEscaneo.resumen.antiguedad}>{t.nuevoEscaneo.dias[`d${a.dias}`]}</Fila>
            <Fila etiqueta={t.nuevoEscaneo.resumen.fuentes}>
              {activas === undefined ? "…" : rellenar(t.nuevoEscaneo.fuentesActivas, { n: activas })}
            </Fila>
            <Fila etiqueta={t.nuevoEscaneo.resumen.nombre}>
              <input
                value={nombre}
                onChange={(ev) => setNombre(ev.target.value)}
                onBlur={() => a.set({ nombre: nombre.trim().slice(0, 60) })}
                maxLength={60}
                className="h-9 w-80 max-w-full rounded-lg border border-border-strong bg-bg px-3 text-sm focus:border-accent"
              />
            </Fila>
          </dl>
        </section>

        <section className="flex flex-col gap-3 rounded-card border border-accent/40 bg-surface p-6 shadow-card">
          <h2 className="text-base font-semibold">{t.nuevoEscaneo.costeTitulo}</h2>
          {estimar.isPending && <p className="text-sm text-ink-faint">{t.nuevoEscaneo.estimando}</p>}
          {estimar.isError && <Aviso tono="mal" titulo={t.comun.algoFallo} />}
          {e && c && (
            <>
              <p className="text-2xl font-bold tabular-nums">
                {rellenar(t.nuevoEscaneo.costeLlamadas, { rango: c.llamadas })}
              </p>
              <p className="text-sm text-ink-soft">
                {rellenar(t.nuevoEscaneo.costeUnidades, { rango: c.tokens })}
                {" · "}
                {t.comun.queSonUnidades}
              </p>
              <p className="text-sm">
                {rellenar(t.nuevoEscaneo.hoyLlevas, { usadas: c.gastadoLlamadas, quedan: c.quedaLlamadas })}
              </p>
              <p className="text-[13px] text-ink-faint">{t.nuevoEscaneo.estimacionAyuda}</p>
            </>
          )}
          {e && !puede && (
            <Aviso tono="mal" titulo={t.nuevoEscaneo.sinPresupuesto}>
              {t.nuevoEscaneo.sinPresupuestoAyuda}
            </Aviso>
          )}
        </section>
      </div>

      <div className="flex items-center justify-between gap-3">
        <BotonSecundario onClick={() => a.set({ paso: a.sinTema ? 1 : 2 })}>
          <ArrowLeft className="size-4" aria-hidden="true" />
          {t.comun.atras}
        </BotonSecundario>
        <AccionPrincipal onClick={lanzar} disabled={!puede || escanear.isPending}>
          <Play className="size-4" aria-hidden="true" />
          {t.nuevoEscaneo.escanear}
        </AccionPrincipal>
      </div>
    </div>
  );
}
