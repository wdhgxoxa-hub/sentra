import { useEffect } from "react";

import { Aviso, BotonSecundario, Pasos } from "@/components/comunes/Comunes";
import type { AccionDePaso } from "@/lib/siguientePaso";
import { modoPorId } from "@/modos/registro";
import type { NichoEnPantalla } from "@/modos/tipos";
import { useAsistenteStore } from "@/stores/asistenteStore";
import { useMultiscanStore } from "@/stores/multiscanStore";
import { useT } from "@/stores/settingsStore";
import { useUiStore } from "@/stores/uiStore";

import { EscaneoEnCurso } from "./nuevo/EscaneoEnCurso";
import { PasoPalabras } from "./nuevo/PasoPalabras";
import { PasoRevisar } from "./nuevo/PasoRevisar";
import { PasoTema } from "./nuevo/PasoTema";
import { ResultadoDeUnEscaneo } from "./nuevo/ResultadoDeUnEscaneo";

/**
 * «Nuevo escaneo» (Fase 2): la pantalla principal. Un asistente de tres
 * pasos (tema → palabras clave → revisar y escanear) y, al escanear, el
 * progreso fuente a fuente. Genérica: los textos del tema los pone el modo.
 */
export function NuevoEscaneo() {
  const t = useT();
  const modo = modoPorId(useUiStore((s) => s.modo));
  const textos = modo.textos(t);
  const a = useAsistenteStore();
  const scan = useMultiscanStore((s) => s.scan);
  const resetEscaneo = useMultiscanStore((s) => s.reset);

  const setView = useUiStore((s) => s.setView);
  const abrirNicho = useUiStore((s) => s.abrirNicho);
  const resultadoSinVer = a.resultadoSinVer;
  const fijar = a.set;
  // D3: al verlo aquí, la marca de la barra lateral se quita.
  useEffect(() => {
    if (resultadoSinVer) fijar({ resultadoSinVer: false });
  }, [resultadoSinVer, fijar]);

  const otroEscaneo = () => {
    resetEscaneo();
    a.reiniciar();
  };
  const alPulsar = (accion: AccionDePaso, nicho?: NichoEnPantalla) => {
    if (accion === "ajustar_palabras") {
      resetEscaneo();
      a.set({ paso: a.sinTema ? 1 : 2 });
    } else if (accion === "abrir_nicho" && nicho) abrirNicho(nicho.id);
    else if (accion === "abrir_radar") setView("radar");
    else if (accion === "abrir_configuracion") setView("settings");
  };

  if (scan.status === "running" || scan.status === "done") {
    const guardado = scan.final?.persisted && scan.runId;
    return (
      <div className="mx-auto flex max-w-[1080px] flex-col gap-6" data-pantalla="escaneo">
        <EscaneoEnCurso
          alTerminar={
            <div className="flex flex-col gap-5">
              {guardado ? (
                <ResultadoDeUnEscaneo
                  runId={scan.runId as string}
                  cancelado={scan.final?.cancelled ?? false}
                  modo={modo}
                  onAccion={alPulsar}
                />
              ) : (
                <Aviso tono="mal" titulo={t.resultado.noGuardado} />
              )}
              <div className="flex justify-end">
                <BotonSecundario onClick={otroEscaneo}>{t.resultado.otroEscaneo}</BotonSecundario>
              </div>
            </div>
          }
        />
      </div>
    );
  }

  const titulo =
    a.paso === 1 ? textos.pregunta : a.paso === 2 ? t.nuevoEscaneo.palabrasTitulo.replace("{tema}", a.tema.trim()) : t.nuevoEscaneo.revisarTitulo;
  const explica = a.paso === 1 ? textos.explica : a.paso === 2 ? null : t.nuevoEscaneo.revisarExplica;

  return (
    <div className="mx-auto flex max-w-[1080px] flex-col gap-6" data-pantalla="nuevo" data-paso={a.paso}>
      <header>
        <h1 className="text-[22px] font-semibold">{titulo}</h1>
        {explica && <p className="mt-1 max-w-[70ch] text-[15px] text-ink-soft">{explica}</p>}
      </header>
      <Pasos
        nombres={[t.nuevoEscaneo.pasos.tema, t.nuevoEscaneo.pasos.palabras, t.nuevoEscaneo.pasos.escanear]}
        actual={a.paso}
      />
      {a.paso === 1 && <PasoTema modo={modo} />}
      {a.paso === 2 && <PasoPalabras />}
      {a.paso === 3 && <PasoRevisar />}
    </div>
  );
}
