/**
 * Nichos de un escaneo, ya adaptados al modo activo (Fase 2, P2)
 * ==============================================================
 *
 * Las pantallas genéricas no saben de veredictos del juez: piden aquí los
 * nichos de un escaneo y reciben `NichoEnPantalla`. Hoy solo existe el modo
 * Software (veredictos del juez); el modo Videos añadirá aquí su lectura.
 */

import { useJudgeTop } from "@/lib/queries";
import { repartirVeredictos } from "@/lib/resultado";
import { nichoDeSoftware } from "@/modos/software";
import type { NichoEnPantalla } from "@/modos/tipos";
import { useSettingsStore } from "@/stores/settingsStore";
import type { NicheVerdict, RunOverview } from "@/types/radar";

export interface NichosDeUnEscaneo {
  cargando: boolean;
  error: unknown;
  /** El escaneo que se enseña y el último juzgado (pueden no ser el mismo). */
  escaneo: RunOverview | null;
  ultimo: RunOverview | null;
  nichos: NichoEnPantalla[];
  descartados: NichoEnPantalla[];
  veredictos: { verdict: NicheVerdict }[];
}

/** `runId` null: el del Radar (el último con nichos). */
export function useNichos(runId: string | null): NichosDeUnEscaneo {
  const idioma = useSettingsStore((s) => s.language);
  const top = useJudgeTop(runId);
  const datos = top.data;
  const { nichos, descartados } = datos
    ? repartirVeredictos(datos.verdicts, datos.rest)
    : { nichos: [], descartados: [] };
  return {
    cargando: top.isPending,
    error: top.error,
    escaneo: datos?.run ?? null,
    ultimo: datos?.latestRun ?? null,
    nichos: nichos.map((v) => nichoDeSoftware(v, idioma)),
    descartados: descartados.map((v) => nichoDeSoftware(v, idioma)),
    veredictos: [...nichos, ...descartados].map((v) => ({ verdict: v.verdict })),
  };
}
