import { Radar as RadarIcon } from "lucide-react";

import { ErrorNotice } from "@/components/ErrorNotice";
import { EvidenceAttributionLine } from "@/components/EvidenceAttributionLine";
import { VERDICT_COLOR, VerdictCard } from "@/components/JudgePanel";
import { SourceBadge } from "@/components/SourceBadge";
import { comoError } from "@/lib/errors";
import { useEvidenceFeed, useJudgeTop, useSources } from "@/lib/queries";
import { useSettingsStore, useT } from "@/stores/settingsStore";
import { nombreDelGrupo, puntuacionDelGrupo } from "@/lib/veredicto";

/** Piezas del feed: las más recientes, sin duplicados. */
const FEED_LIMIT = 40;

/**
 * Radar en vivo (D-C2): todo sale del juez.
 *
 * Arriba el Top 6 con el mismo detalle y la misma consulta que el panel del
 * juez en Fuentes, así que no puede contar otra cosa. Debajo, el resto de
 * veredictos de esa ejecución en el mismo orden. Al final, la evidencia
 * más reciente, siempre con su atribución. Lo que no está juzgado no se
 * presenta como oportunidad.
 */
export function RadarViewPage() {
  const t = useT();
  const idioma = useSettingsStore((s) => s.language);
  const top = useJudgeTop(null);
  const feed = useEvidenceFeed(FEED_LIMIT);
  const fuentes = useSources();
  const nombre = (id: string) =>
    fuentes.data?.sources.find((c) => c.source === id)?.displayName ?? id;

  return (
    <div className="flex flex-col gap-8">
      <section aria-labelledby="top-juez" className="flex flex-col gap-3">
        <header>
          <h2 id="top-juez" className="flex items-center gap-2 text-base font-semibold">
            <RadarIcon className="size-4 text-accent" aria-hidden="true" />
            {t.radar.title.replace("{target}", String(top.data?.target ?? 6))}
          </h2>
          <p className="mt-0.5 text-xs text-ink-soft">{t.radar.subtitle}</p>
        </header>

        {top.isPending && <p className="text-sm text-ink-faint">{t.radar.loading}</p>}
        {top.isError && <ErrorNotice {...comoError(top.error)} title={t.radar.error} />}
        {top.data && top.data.verdicts.length === 0 && (
          <div className="rounded-card border border-dashed border-border p-8 text-center">
            <p className="text-sm font-medium">{top.data.reason ?? t.radar.empty}</p>
            <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-ink-soft">
              {t.radar.emptyHint}
            </p>
          </div>
        )}
        {top.data && top.data.verdicts.length > 0 && (
          <>
            <p className="text-xs text-ink-soft">
              {t.judge.buildCount
                .replace("{count}", String(top.data.buildCount))
                .replace("{target}", String(top.data.target))}
              {top.data.reason && <span className="block text-ink-faint">{top.data.reason}</span>}
            </p>
            {top.data.verdicts.map((v) => (
              <VerdictCard key={v.id} v={v} t={t} nombre={nombre} actuales={top.data.currentVersions} />
            ))}
          </>
        )}
      </section>

      {top.data && top.data.rest.length > 0 && (
        <section aria-labelledby="resto-veredictos">
          <header className="mb-3">
            <h2 id="resto-veredictos" className="text-base font-semibold">
              {t.radar.restTitle.replace("{n}", String(top.data.rest.length))}
            </h2>
            <p className="mt-0.5 text-xs text-ink-soft">{t.radar.restSubtitle}</p>
          </header>
          <ul className="divide-y divide-border rounded-card border border-border bg-surface">
            {top.data.rest.map((v) => (
              <li key={v.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
                <span className={`rounded-lg border px-2 py-0.5 text-[11px] font-semibold ${VERDICT_COLOR[v.verdict]}`}>
                  {t.judge.verdict[v.verdict]}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm">
                  {nombreDelGrupo(v, t.judge.noCommonProblem, idioma)}
                </span>
                <span className="text-[11px] text-ink-faint">
                  {t.radar.members.replace("{n}", String(v.memberCount))}
                  {v.missing.length > 0 && ` · ${t.judge.missing.replace("{gates}", v.missing.join(", "))}`}
                </span>
                {puntuacionDelGrupo(v, t.judge.score) && (
                  <span className="font-mono text-xs tabular-nums">{puntuacionDelGrupo(v, t.judge.score)}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="feed">
        <header className="mb-3">
          <h2 id="feed" className="text-base font-semibold">
            {t.radar.feedTitle}
          </h2>
          <p className="mt-0.5 text-xs text-ink-soft">{t.radar.feedSubtitle}</p>
        </header>

        {feed.isPending && <p className="text-sm text-ink-faint">{t.radar.loading}</p>}
        {feed.isError && <ErrorNotice {...comoError(feed.error)} title={t.radar.feedError} />}
        {feed.data?.items.length === 0 && (
          <p className="rounded-card border border-dashed border-border p-6 text-center text-sm text-ink-soft">
            {t.radar.feedEmpty}
          </p>
        )}
        {feed.data && feed.data.items.length > 0 && (
          <ul className="divide-y divide-border rounded-card border border-border bg-surface">
            {feed.data.items.map((e) => (
              <li key={e.id} className="flex flex-col gap-1 px-4 py-3">
                <p className="line-clamp-2 text-sm">{e.title ?? e.excerpt}</p>
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-ink-faint">
                  <EvidenceAttributionLine attribution={e.attribution} />
                  <span aria-hidden="true">·</span>
                  <time dateTime={e.createdAt}>{new Date(e.createdAt).toLocaleDateString()}</time>
                  <SourceBadge source={e.dataSource} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
