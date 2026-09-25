import { Pasos, BotonSecundario } from "@/components/comunes/Comunes";
import { modoPorId } from "@/modos/registro";
import { useAsistenteStore } from "@/stores/asistenteStore";
import { useMultiscanStore } from "@/stores/multiscanStore";
import { useT } from "@/stores/settingsStore";
import { useUiStore } from "@/stores/uiStore";

import { EscaneoEnCurso } from "./nuevo/EscaneoEnCurso";
import { PasoPalabras } from "./nuevo/PasoPalabras";
import { PasoRevisar } from "./nuevo/PasoRevisar";
import { PasoTema } from "./nuevo/PasoTema";

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

  if (scan.status === "running" || scan.status === "done") {
    return (
      <div className="mx-auto flex max-w-[1080px] flex-col gap-6" data-pantalla="escaneo">
        <EscaneoEnCurso
          alTerminar={
            <div className="flex justify-end">
              <BotonSecundario
                onClick={() => {
                  resetEscaneo();
                  a.reiniciar();
                }}
              >
                {t.resultado.otroEscaneo}
              </BotonSecundario>
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
