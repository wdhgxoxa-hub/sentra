import { ArrowRight } from "lucide-react";

import { AccionPrincipal } from "@/components/comunes/Comunes";
import type { IdiomaDeBusqueda } from "@/lib/cobertura";
import type { Modo } from "@/modos/tipos";
import { DIAS, useAsistenteStore } from "@/stores/asistenteStore";
import { useT } from "@/stores/settingsStore";

const IDIOMAS: IdiomaDeBusqueda[] = ["es", "en"];

function Opcion({ activa, onClick, children }: { activa: boolean; onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      aria-pressed={activa}
      onClick={onClick}
      className={`h-9 rounded-full border px-4 text-sm font-medium transition-colors ${
        activa ? "border-accent bg-accent-soft text-ink" : "border-border-strong text-ink-soft hover:bg-surface-2"
      }`}
    >
      {activa ? `✓ ${children}` : children}
    </button>
  );
}

/** Paso 1: el tema, contado como a una persona, los idiomas y hasta cuándo mirar. */
export function PasoTema({ modo }: { modo: Modo }) {
  const t = useT();
  const textos = modo.textos(t);
  const a = useAsistenteStore();
  const puedeSeguir = a.sinTema || a.tema.trim().length > 0;
  const alternar = (idioma: IdiomaDeBusqueda) => {
    const siguientes = a.idiomas.includes(idioma) ? a.idiomas.filter((i) => i !== idioma) : [...a.idiomas, idioma];
    if (siguientes.length > 0) a.set({ idiomas: siguientes });
  };
  const seguir = () => {
    if (!puedeSeguir) return;
    a.set({ paso: a.sinTema ? 3 : 2, nombre: a.nombre || a.tema.trim().slice(0, 60) });
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        seguir();
      }}
      className="flex flex-col gap-6 rounded-card border border-accent/40 bg-surface p-6 shadow-card"
    >
      <label className="flex flex-col gap-2">
        <span className="text-sm font-semibold">{t.nuevoEscaneo.temaEtiqueta}</span>
        <input
          data-campo="tema"
          value={a.tema}
          onChange={(e) => a.set({ tema: e.target.value })}
          disabled={a.sinTema}
          placeholder={textos.ejemplo}
          maxLength={200}
          autoFocus
          className="h-12 rounded-lg border border-border-strong bg-bg px-4 text-[17px] text-ink transition-colors focus:border-accent disabled:opacity-50"
        />
        <span className="text-[13px] text-ink-faint">{textos.ejemplos}</span>
      </label>

      <div className="grid gap-6 sm:grid-cols-2">
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-sm font-semibold">{t.nuevoEscaneo.idiomas}</legend>
          <div className="flex flex-wrap gap-2">
            {IDIOMAS.map((idioma) => (
              <Opcion key={idioma} activa={a.idiomas.includes(idioma)} onClick={() => alternar(idioma)}>
                {t.nuevoEscaneo.idioma[idioma]}
              </Opcion>
            ))}
          </div>
          <span className="text-[13px] text-ink-faint">{t.nuevoEscaneo.idiomasAyuda}</span>
        </fieldset>
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-sm font-semibold">{t.nuevoEscaneo.antiguedad}</legend>
          <div className="flex flex-wrap gap-2">
            {DIAS.map((dias) => (
              <Opcion key={dias} activa={a.dias === dias} onClick={() => a.set({ dias })}>
                {t.nuevoEscaneo.dias[`d${dias}`]}
              </Opcion>
            ))}
          </div>
          <span className="text-[13px] text-ink-faint">{t.nuevoEscaneo.antiguedadAyuda}</span>
        </fieldset>
      </div>

      <details className="text-sm">
        <summary className="cursor-pointer select-none font-medium text-ink-soft">{t.nuevoEscaneo.masOpciones}</summary>
        <label className="mt-3 flex items-start gap-2 text-ink-soft">
          <input
            type="checkbox"
            className="mt-1"
            checked={a.sinTema}
            onChange={(e) => a.set({ sinTema: e.target.checked })}
          />
          {t.nuevoEscaneo.sinTema}
        </label>
      </details>

      <div className="flex justify-end">
        <AccionPrincipal type="submit" disabled={!puedeSeguir}>
          {a.sinTema ? t.nuevoEscaneo.irAEscanear : t.nuevoEscaneo.irAPalabras}
          <ArrowRight className="size-4" aria-hidden="true" />
        </AccionPrincipal>
      </div>
    </form>
  );
}
