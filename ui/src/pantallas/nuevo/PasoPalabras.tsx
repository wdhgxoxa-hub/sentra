import { ArrowLeft, ArrowRight, Sparkles, X } from "lucide-react";
import { useState } from "react";

import { AccionPrincipal, Aviso, BotonSecundario } from "@/components/comunes/Comunes";
import { coberturaDePalabras, palabrasDistintas, type IdiomaDeBusqueda } from "@/lib/cobertura";
import { useProposeKeywords } from "@/lib/queries";
import { rellenar, unirIdiomas } from "@/lib/texto";
import { useAsistenteStore } from "@/stores/asistenteStore";
import { useT } from "@/stores/settingsStore";

type T = ReturnType<typeof useT>;

/** Por qué la propuesta fue básica, en palabras: sin clave, sin presupuesto o un error. */
function motivoDeLaBasica(t: T, motivo: string | null): string {
  if (motivo === "gemini_not_configured") return t.nuevoEscaneo.motivoBasica.gemini_not_configured;
  if (motivo?.startsWith("tope_")) return t.nuevoEscaneo.motivoBasica.tope;
  return t.nuevoEscaneo.motivoBasica.error;
}

function FilaDeIdioma({ idioma }: { idioma: IdiomaDeBusqueda }) {
  const t = useT();
  const a = useAsistenteStore();
  const [nueva, setNueva] = useState("");
  const nombreIdioma = t.nuevoEscaneo.idioma[idioma];
  const palabras = a.palabras[idioma];
  const poner = (lista: string[]) => a.set({ palabras: { ...a.palabras, [idioma]: palabrasDistintas(lista) } });
  const anadir = () => {
    if (!nueva.trim()) return;
    poner([...palabras, nueva]);
    setNueva("");
  };

  return (
    <div className="flex flex-col gap-2" data-idioma={idioma}>
      <p className="text-[13px] font-semibold uppercase tracking-wide text-ink-faint">
        {nombreIdioma} · {palabrasDistintas(palabras).length}
      </p>
      <ul className="flex flex-wrap gap-2">
        {palabras.map((palabra) => (
          <li
            key={palabra}
            className="flex h-9 items-center gap-1 rounded-full border border-border-strong bg-surface-2 pl-4 pr-1 text-sm"
          >
            {palabra}
            <button
              type="button"
              onClick={() => poner(palabras.filter((p) => p !== palabra))}
              aria-label={rellenar(t.nuevoEscaneo.quitar, { palabra })}
              className="grid size-7 place-items-center rounded-full text-ink-faint hover:bg-surface hover:text-ink"
            >
              <X className="size-4" aria-hidden="true" />
            </button>
          </li>
        ))}
        {palabras.length === 0 && (
          <li className="text-sm text-ink-faint">{rellenar(t.nuevoEscaneo.sinPalabras, { idioma: nombreIdioma.toLowerCase() })}</li>
        )}
      </ul>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          anadir();
        }}
        className="flex gap-2"
      >
        <input
          value={nueva}
          onChange={(e) => setNueva(e.target.value)}
          maxLength={60}
          placeholder={rellenar(t.nuevoEscaneo.anadirAyuda, { idioma: nombreIdioma.toLowerCase() })}
          className="h-9 flex-1 rounded-lg border border-border-strong bg-bg px-3 text-sm focus:border-accent"
        />
        <BotonSecundario onClick={anadir} disabled={!nueva.trim()}>
          {t.nuevoEscaneo.anadir}
        </BotonSecundario>
      </form>
    </div>
  );
}

/** Paso 2: las búsquedas por idioma, propuestas o escritas, con su aviso de cobertura. */
export function PasoPalabras() {
  const t = useT();
  const a = useAsistenteStore();
  const proponer = useProposeKeywords();
  const cobertura = coberturaDePalabras(a.palabras, a.idiomas);
  // «en español ni en inglés» / «en español y en inglés», no «en español, inglés».
  const nombres = (idiomas: IdiomaDeBusqueda[], nexo: string) =>
    unirIdiomas(idiomas.map((i) => t.nuevoEscaneo.idioma[i].toLowerCase()), nexo);

  const pedirPropuesta = () =>
    proponer.mutate(
      { topic: a.tema.trim(), languages: a.idiomas },
      {
        onSuccess: (r) =>
          a.set({
            propuesta: { origin: r.origin, reason: r.reason },
            // Medida B (Fase 3): qué fuentes encajan con este tema.
            tipoDeTema: r.topicKind,
            sitiosStackExchange: r.stackexchangeSites,
            temaDeLaPropuesta: a.tema.trim(),
            palabras: {
              es: palabrasDistintas([...a.palabras.es, ...r.keywords.es]),
              en: palabrasDistintas([...a.palabras.en, ...r.keywords.en]),
            },
          }),
      },
    );

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-5 rounded-card border border-border bg-surface p-6 shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-ink-soft">{t.nuevoEscaneo.palabrasExplica}</p>
          <div className="flex items-center gap-2">
            <span className="text-[13px] text-ink-faint">{t.nuevoEscaneo.proponerCoste}</span>
            <BotonSecundario onClick={pedirPropuesta} disabled={proponer.isPending}>
              <Sparkles className="size-4" aria-hidden="true" />
              {proponer.isPending
                ? t.nuevoEscaneo.proponiendo
                : a.propuesta
                  ? t.nuevoEscaneo.proponerOtraVez
                  : t.nuevoEscaneo.proponer}
            </BotonSecundario>
          </div>
        </div>
        {a.propuesta?.origin === "gemini" && <p className="text-sm text-ok">{t.nuevoEscaneo.propuestasGemini}</p>}
        {a.propuesta?.origin === "local" && (
          <Aviso tono="info" titulo={t.nuevoEscaneo.propuestaBasica}>
            {motivoDeLaBasica(t, a.propuesta.reason)}
          </Aviso>
        )}
        {proponer.isError && <Aviso tono="mal" titulo={t.comun.algoFallo} />}
        {a.idiomas.map((idioma) => (
          <FilaDeIdioma key={idioma} idioma={idioma} />
        ))}
      </div>

      {cobertura.nivel === "buena" ? (
        <Aviso tono="bien" titulo={rellenar(t.nuevoEscaneo.coberturaBuena, { n: cobertura.total })} />
      ) : (
        <Aviso tono="aviso" titulo={t.nuevoEscaneo.coberturaBaja}>
          <ul className="list-disc pl-5">
            {cobertura.motivos.map((motivo) => (
              <li key={motivo}>
                {rellenar(t.nuevoEscaneo.motivo[motivo], {
                  n: motivo === "largas" ? cobertura.largas.length : cobertura.total,
                  lista: cobertura.largas.map((p) => `«${p}»`).join(", "),
                  idiomas:
                    motivo === "idioma_escaso"
                      ? nombres(cobertura.escasos, t.nuevoEscaneo.nexoY)
                      : nombres(cobertura.sinPalabras, t.nuevoEscaneo.nexoNi),
                })}
              </li>
            ))}
          </ul>
        </Aviso>
      )}

      <div className="flex items-center justify-between gap-3">
        <BotonSecundario onClick={() => a.set({ paso: 1 })}>
          <ArrowLeft className="size-4" aria-hidden="true" />
          {t.comun.atras}
        </BotonSecundario>
        <AccionPrincipal onClick={() => a.set({ paso: 3 })} disabled={cobertura.total === 0}>
          {t.nuevoEscaneo.irAEscanear}
          <ArrowRight className="size-4" aria-hidden="true" />
        </AccionPrincipal>
      </div>
    </div>
  );
}
