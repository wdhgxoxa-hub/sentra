import { EvidenceAttributionLine } from "@/components/EvidenceAttributionLine";
import { VerdictCard } from "@/components/detalle/VerdictCard";
import { useEvidenceFeed, useJudgeTop, useSources } from "@/lib/queries";
import { useNichos } from "@/lib/nichos";
import { avisoDelUltimoEscaneo } from "@/lib/radar";
import type { AccionDePaso } from "@/lib/siguientePaso";
import { modoPorId } from "@/modos/registro";
import { FichaDeNicho } from "@/pantallas/FichaDeNicho";
import { Radar } from "@/pantallas/Radar";
import { useAsistenteStore } from "@/stores/asistenteStore";
import { useT } from "@/stores/settingsStore";
import { useUiStore } from "@/stores/uiStore";

/** Piezas del feed: las más recientes, sin duplicados. */
const FEED_LIMIT = 40;

/** Lo último que han traído las fuentes, plegado: no son nichos (el juez no lo ha visto). */
function EvidenciaReciente() {
  const t = useT();
  const feed = useEvidenceFeed(FEED_LIMIT);
  const items = feed.data?.items ?? [];
  return (
    <details className="rounded-card border border-border bg-surface p-5 text-sm">
      <summary className="cursor-pointer select-none font-semibold">
        {t.radar.evidencia.replace("{n}", String(items.length))}
      </summary>
      <p className="mt-2 text-ink-soft">{t.radar.evidenciaExplica}</p>
      {feed.isError && <p className="mt-2 text-danger">{t.radar.evidenciaError}</p>}
      {feed.data && items.length === 0 && <p className="mt-2 text-ink-soft">{t.radar.evidenciaVacia}</p>}
      <ul className="mt-3 divide-y divide-border" aria-labelledby="feed">
        {items.map((e) => (
          <li key={e.id} data-evidencia={e.id} className="flex flex-col gap-1 py-2.5">
            <p className="line-clamp-2">{e.title ?? e.excerpt}</p>
            <div className="flex flex-wrap items-center gap-2 text-[13px] text-ink-faint">
              <EvidenceAttributionLine attribution={e.attribution} />
              <span aria-hidden="true">·</span>
              <time dateTime={e.createdAt}>{new Date(e.createdAt).toLocaleDateString()}</time>
            </div>
          </li>
        ))}
      </ul>
    </details>
  );
}

/**
 * Radar del modo Software: lee los nichos (lib/nichos.ts) y pinta las
 * pantallas genéricas (pantallas/Radar, pantallas/FichaDeNicho). El detalle
 * técnico del juez solo va dentro de «Ver detalle» de la ficha.
 */
export function RadarViewPage() {
  const t = useT();
  const modo = modoPorId(useUiStore((s) => s.modo));
  const datos = useNichos(null);
  const top = useJudgeTop(null);
  const fuentes = useSources();
  const abierto = useUiStore((s) => s.nichoAbierto);
  const abrirNicho = useUiStore((s) => s.abrirNicho);
  const setView = useUiStore((s) => s.setView);
  const asistente = useAsistenteStore();
  const nombreDeFuente = (id: string) => fuentes.data?.sources.find((c) => c.source === id)?.displayName ?? id;

  const alPulsar = (accion: AccionDePaso) => {
    if (accion === "ajustar_palabras") {
      asistente.set({ paso: asistente.tema.trim() ? 2 : 1 });
      setView("nuevo");
    } else if (accion === "abrir_configuracion") setView("settings");
    else if (accion === "abrir_radar") abrirNicho(null);
  };

  const nicho = abierto ? [...datos.nichos, ...datos.descartados].find((n) => n.id === abierto) : undefined;
  const veredicto = abierto && top.data ? [...top.data.verdicts, ...top.data.rest].find((v) => v.id === abierto) : undefined;
  if (nicho) {
    return (
      <FichaDeNicho
        nicho={nicho}
        modo={modo}
        onVolver={() => abrirNicho(null)}
        detalle={
          veredicto &&
          top.data && <VerdictCard v={veredicto} t={t} nombre={nombreDeFuente} actuales={top.data.currentVersions} />
        }
      />
    );
  }

  return (
    <Radar
      modo={modo}
      nichos={datos.nichos}
      descartados={datos.descartados}
      escaneo={datos.escaneo}
      aviso={top.data ? avisoDelUltimoEscaneo(top.data) : null}
      cargando={datos.cargando}
      fallo={Boolean(datos.error)}
      evidencia={<EvidenciaReciente />}
      onNuevo={() => setView("nuevo")}
      onAbrir={(id) => abrirNicho(id)}
      onAccion={alPulsar}
    />
  );
}
