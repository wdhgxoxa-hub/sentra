import { Radar, RadioTower, Search, Settings } from "lucide-react";

import isotipo from "@/assets/isotipo.png";
import { HealthIndicator } from "@/components/HealthIndicator";
import { useSources } from "@/lib/queries";
import { useT } from "@/stores/settingsStore";
import { useUiStore, type RadarView } from "@/stores/uiStore";

const ICONS = {
  radar: Radar,
  search: Search,
  sources: RadioTower,
  settings: Settings,
} as const;

const ITEMS: RadarView[] = ["radar", "search", "sources", "settings"];

/**
 * «X de N fuentes activas». N es el catálogo real del motor, no una cifra
 * prometida; sin respuesta del motor no se inventa ningún número.
 */
function SourcesSummary() {
  const t = useT();
  const setView = useUiStore((state) => state.setView);
  const fuentes = useSources();
  const lista = fuentes.data?.sources;
  const texto = lista
    ? t.sources.activeSummary
        .replace("{active}", String(lista.filter((s) => s.active).length))
        .replace("{total}", String(lista.length))
    : t.sources.summaryUnknown;
  return (
    <button
      type="button"
      onClick={() => setView("sources")}
      className="mb-2 w-full rounded-lg px-2.5 py-1.5 text-left text-[11px] text-ink-soft transition-colors hover:bg-surface-2 hover:text-ink"
    >
      {texto}
    </button>
  );
}

/** Navegación principal: el escaneo vive en Fuentes (D-C2). */
export function Sidebar() {
  const t = useT();
  const view = useUiStore((state) => state.view);
  const setView = useUiStore((state) => state.setView);

  return (
    <nav
      aria-label={t.app.name}
      className="flex w-56 shrink-0 flex-col gap-1 border-r border-border bg-surface p-3"
    >
      {/* El isotipo lleva su propio color de marca, asi que se sostiene igual
          sobre el fondo claro y sobre el oscuro. El nombre y el eslogan si
          dependen del tema y usan los tonos de tinta.

          El eslogan va debajo y no al lado: junto al nombre le quedaban unos
          140 px y se partia en tres lineas cortas; a lo ancho del rail entra
          en dos y se lee de un vistazo. */}
      <div className="drag-region mb-6 px-2 pt-1">
        <div className="flex items-center gap-3">
          <img
            src={isotipo}
            alt=""
            width={46}
            height={46}
            draggable={false}
            className="size-[46px] shrink-0 select-none"
          />
          <p className="text-[20px] font-bold leading-none tracking-[0.22em] text-ink">
            {t.app.name}
          </p>
        </div>
        <p className="mt-3 text-[11px] font-medium leading-relaxed text-ink-soft">
          {t.app.tagline}
        </p>
      </div>

      <ul className="flex flex-col gap-0.5">
        {ITEMS.map((item) => {
          const Icon = ICONS[item];
          const active = view === item;
          return (
            <li key={item}>
              <button
                type="button"
                onClick={() => setView(item)}
                aria-current={active ? "page" : undefined}
                className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors ${
                  active
                    ? "bg-accent-soft font-medium text-accent"
                    : "text-ink-soft hover:bg-surface-2 hover:text-ink"
                }`}
              >
                <Icon className="size-4 shrink-0" aria-hidden="true" />
                <span className="truncate">{t.nav[item]}</span>
              </button>
            </li>
          );
        })}
      </ul>

      <div className="mt-auto border-t border-border pt-3">
        <SourcesSummary />
        <HealthIndicator />
      </div>
    </nav>
  );
}
