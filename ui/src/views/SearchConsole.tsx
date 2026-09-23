import { Search as SearchIcon, Sparkles, Type } from "lucide-react";

import { Explain } from "@/components/Explain";
import { ErrorNotice } from "@/components/ErrorNotice";
import { SourceBadge } from "@/components/SourceBadge";
import { UrgencyBadge } from "@/components/UrgencyBadge";
import { comoError } from "@/lib/errors";
import { useHybridSearch } from "@/lib/queries";
import { useT } from "@/stores/settingsStore";
import { useUiStore } from "@/stores/uiStore";
import type { HybridSearchHit } from "@/types/radar";

/**
 * Consola de búsqueda híbrida.
 *
 * Enseña POR QUÉ apareció cada resultado: si lo encontró la búsqueda por
 * significado, la de palabras exactas, o ambas. Esa distinción es lo que
 * separa una consola de investigación de una caja negra, y además explica
 * los casos raros: una consulta sin vocabulario común que aun así acierta,
 * o un nombre propio que solo rescata la búsqueda léxica.
 */
export function SearchConsole() {
  const t = useT();
  const searchQuery = useUiStore((state) => state.searchQuery);
  const setSearchQuery = useUiStore((state) => state.setSearchQuery);
  const results = useHybridSearch({ query: searchQuery, limit: 20 });

  const examples = [
    t.search.examples.billing,
    t.search.examples.migration,
    t.search.examples.support,
    t.search.examples.pricing,
  ];

  const routeOf = (hit: HybridSearchHit) => {
    if (hit.denseRank !== null && hit.bm25Rank !== null) return "both";
    return hit.denseRank !== null ? "semantic" : "exact";
  };

  return (
    <div className="flex max-w-4xl flex-col gap-5">
      <header>
        <h2 className="text-base font-semibold">{t.search.title}</h2>
        <p className="mt-0.5 text-xs text-ink-soft">
          {t.search.subtitle}
        </p>
      </header>

      <div className="relative">
        <SearchIcon
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-faint"
          aria-hidden="true"
        />
        <input
          type="search"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder={t.search.placeholder}
          aria-label={t.search.title}
          className="w-full rounded-lg border border-border bg-surface py-2.5 pl-9 pr-3 text-sm transition-colors focus:border-accent"
        />
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-ink-faint">
          {t.search.suggestions}
        </span>
        {examples.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => setSearchQuery(example)}
            className="rounded-full border border-border px-2.5 py-1 text-xs text-ink-soft transition-colors hover:border-accent hover:text-accent"
          >
            {example}
          </button>
        ))}
      </div>

      {results.isError && !results.isFetching && (
        <ErrorNotice {...comoError(results.error)} title={t.search.error} />
      )}

      {results.isFetching && (
        <p className="text-sm text-ink-faint">{t.search.searching}</p>
      )}

      {results.data?.length === 0 && !results.isFetching && (
        <div className="rounded-card border border-dashed border-border p-6 text-center">
          <p className="text-sm font-medium">{t.search.empty}</p>
          <p className="mt-1 text-xs text-ink-soft">
            {t.search.emptyHint}
          </p>
        </div>
      )}

      {results.data && results.data.length > 0 && (
        <div className="overflow-hidden rounded-card border border-border bg-surface">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-surface-2 text-left text-[11px] uppercase tracking-wide text-ink-faint">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t.search.colText}
                </th>
                <th scope="col" className="px-2 py-2 font-medium">
                  <span className="inline-flex items-center gap-1">
                    <Sparkles className="size-3" aria-hidden="true" />
                    {t.search.colSemantic}
                    <Explain
                      title={t.explain.semantic.title}
                      body={t.explain.semantic.body}
                    />
                  </span>
                </th>
                <th scope="col" className="px-2 py-2 font-medium">
                  <span className="inline-flex items-center gap-1">
                    <Type className="size-3" aria-hidden="true" />
                    {t.search.colExact}
                    <Explain
                      title={t.explain.exact.title}
                      body={t.explain.exact.body}
                    />
                  </span>
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  <span className="inline-flex items-center gap-1">
                    {t.search.colCombined}
                    <Explain
                      title={t.explain.rrf.title}
                      body={t.explain.rrf.body}
                      align="end"
                    />
                  </span>
                </th>
              </tr>
            </thead>

            <tbody className="divide-y divide-border">
              {results.data.map((hit) => {
                const route = routeOf(hit);
                return (
                  <tr key={hit.id} className="hover:bg-surface-2">
                    <td className="max-w-md px-3 py-2.5">
                      <p className="truncate">{hit.text}</p>
                      <p className="mt-0.5 flex items-center gap-2 text-[11px] text-ink-faint">
                        <span className="font-mono">r/{hit.subreddit}</span>
                        <SourceBadge source={hit.dataSource} />
                        <span aria-hidden="true">·</span>
                        <span
                          className={
                            route === "both"
                              ? "text-accent"
                              : route === "semantic"
                                ? "text-ok"
                                : "text-warn"
                          }
                        >
                          {route === "both"
                            ? t.search.both
                            : route === "semantic"
                              ? t.search.onlySemantic
                              : t.search.onlyExact}
                        </span>
                      </p>
                    </td>
                    <td className="px-2 py-2.5 font-mono text-xs tabular-nums text-ink-soft">
                      {hit.denseRank ?? "—"}
                    </td>
                    <td className="px-2 py-2.5 font-mono text-xs tabular-nums text-ink-soft">
                      {hit.bm25Rank ?? "—"}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <UrgencyBadge tier={hit.urgencyTier} />
                        <span className="font-mono text-xs tabular-nums">
                          {hit.rrfScore.toFixed(5)}
                        </span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
