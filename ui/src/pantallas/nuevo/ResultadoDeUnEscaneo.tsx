import { ResultadoDelEscaneo } from "@/components/nicho/ResultadoDelEscaneo";
import { useNichos } from "@/lib/nichos";
import { useSources } from "@/lib/queries";
import { fuenteDominante } from "@/lib/resultado";
import type { AccionDePaso } from "@/lib/siguientePaso";
import { siguientePaso } from "@/lib/siguientePaso";
import type { Modo, NichoEnPantalla } from "@/modos/tipos";
import { useT } from "@/stores/settingsStore";

/**
 * El resultado de un escaneo ya juzgado: lee sus nichos (y si hay un escaneo
 * anterior con nichos, que el Radar sigue enseñando) y dice qué hacer.
 */
export function ResultadoDeUnEscaneo({
  runId,
  cancelado,
  modo,
  onAccion,
  incrustado = false,
}: {
  incrustado?: boolean;
  runId: string;
  cancelado: boolean;
  modo: Modo;
  onAccion: (accion: AccionDePaso, nicho?: NichoEnPantalla) => void;
}) {
  const t = useT();
  const deEste = useNichos(runId);
  const delRadar = useNichos(null);
  const fuentes = useSources();
  if (deEste.cargando) return <p className="text-sm text-ink-faint">{t.comun.cargando}</p>;
  if (!deEste.escaneo) return <p className="text-sm text-ink-faint">{t.comun.algoFallo}</p>;
  const hayNichoAnterior =
    delRadar.escaneo !== null && delRadar.escaneo.runId !== runId && delRadar.escaneo.niches > 0;
  const dominante = fuenteDominante(deEste.escaneo.sources);
  const nombreDe = (id: string) => fuentes.data?.sources.find((c) => c.source === id)?.displayName ?? id;
  const siguiente = siguientePaso({
    escaneo: deEste.escaneo,
    veredictos: deEste.veredictos,
    cancelado,
    hayNichoAnterior,
  });
  return (
    <ResultadoDelEscaneo
      siguiente={siguiente}
      nichos={deEste.nichos}
      descartados={deEste.descartados}
      modo={modo}
      onAccion={onAccion}
      incrustado={incrustado}
      dominante={dominante && { nombre: nombreDe(dominante.fuente), piezas: dominante.piezas, total: dominante.total }}
    />
  );
}
