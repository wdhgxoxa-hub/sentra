import { useHybridSearch } from "@/lib/queries";
import { useUiStore } from "@/stores/uiStore";

/**
 * Consola de busqueda hibrida.
 *
 * Muestra el desglose RRF (rango denso y rango lexico) junto a cada
 * resultado: ver POR QUE aparecio algo es lo que separa una consola de
 * investigacion de una caja negra.
 */
export function SearchConsole() {
  const searchQuery = useUiStore((state) => state.searchQuery);
  const setSearchQuery = useUiStore((state) => state.setSearchQuery);
  const results = useHybridSearch({ query: searchQuery, limit: 20 });

  return (
    <div className="flex flex-col gap-4">
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium">Buscar puntos de dolor</span>
        <input
          type="search"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder="no puedo exportar facturas"
          className="rounded-md border border-[--color-border-subtle] bg-[--color-surface-raised] px-3 py-2 text-sm"
        />
      </label>

      {results.isFetching && (
        <p className="text-sm text-[--color-ink-muted]">Buscando...</p>
      )}

      <table className="w-full text-sm">
        <thead className="text-left text-xs uppercase text-[--color-ink-muted]">
          <tr>
            <th scope="col" className="py-1">
              Texto
            </th>
            <th scope="col" className="py-1">
              Denso
            </th>
            <th scope="col" className="py-1">
              BM25
            </th>
            <th scope="col" className="py-1">
              RRF
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[--color-border-subtle]">
          {results.data?.map((hit) => (
            <tr key={hit.id}>
              <td className="max-w-md truncate py-2">{hit.text}</td>
              <td className="py-2 font-mono tabular-nums">
                {hit.denseRank ?? "-"}
              </td>
              <td className="py-2 font-mono tabular-nums">
                {hit.bm25Rank ?? "-"}
              </td>
              <td className="py-2 font-mono tabular-nums">
                {hit.rrfScore.toFixed(5)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
