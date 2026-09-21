import { Explain } from "@/components/Explain";
import { useT } from "@/stores/settingsStore";
import { SCORE_WEIGHTS, type ScoreBreakdown } from "@/types/radar";

/**
 * De dónde sale la puntuación.
 *
 * Se muestra como barras y no como un número suelto porque un 73.5 no
 * explica nada: lo que informa es «difusión al máximo, frecuencia baja»,
 * que significa que el problema está extendido pero aún no es recurrente.
 *
 * Cada factor lleva su explicación al lado. Son cinco conceptos que nadie
 * tiene por qué conocer, y sin ellos la tabla es decoración.
 */
export function ScoreBreakdownBars({ breakdown }: { breakdown: ScoreBreakdown }) {
  const t = useT();

  const rows: Array<{
    key: keyof typeof SCORE_WEIGHTS;
    label: string;
    help: { title: string; body: string };
  }> = [
    { key: "spreadFactor", label: t.explain.spread.title, help: t.explain.spread },
    {
      key: "frequencyFactor",
      label: t.explain.frequency.title,
      help: t.explain.frequency,
    },
    {
      key: "severityFactor",
      label: t.explain.severity.title,
      help: t.explain.severity,
    },
    { key: "recencyFactor", label: t.explain.recency.title, help: t.explain.recency },
    {
      key: "paidSignalFactor",
      label: t.explain.paidSignal.title,
      help: t.explain.paidSignal,
    },
  ];

  return (
    <table className="w-full text-sm">
      <caption className="sr-only">{t.detail.breakdown}</caption>
      <tbody>
        {rows.map(({ key, label, help }) => {
          const factor = breakdown[key];
          const points = factor * SCORE_WEIGHTS[key] * 100;
          const maxPoints = SCORE_WEIGHTS[key] * 100;

          return (
            <tr key={key}>
              <th
                scope="row"
                className="w-40 py-1.5 pr-3 text-left text-xs font-normal text-ink-soft"
              >
                <span className="inline-flex items-center gap-1">
                  {label}
                  <Explain title={help.title} body={help.body} />
                </span>
              </th>
              <td className="w-full py-1.5">
                <div className="h-1.5 rounded-full bg-surface-2">
                  <div
                    className="h-1.5 rounded-full bg-accent transition-[width] duration-500 ease-out"
                    style={{ width: `${Math.round(factor * 100)}%` }}
                  />
                </div>
              </td>
              <td className="whitespace-nowrap py-1.5 pl-3 text-right font-mono text-xs tabular-nums text-ink-soft">
                {points.toFixed(1)}
                <span className="text-ink-faint">
                  /{maxPoints.toFixed(0)}
                </span>
              </td>
            </tr>
          );
        })}

        <tr className="border-t border-border">
          <th scope="row" className="py-2 pr-3 text-left text-sm font-semibold">
            {t.detail.total}
          </th>
          <td />
          <td className="py-2 pl-3 text-right font-mono text-sm font-semibold tabular-nums">
            {breakdown.finalScore.toFixed(1)}
            <span className="text-ink-faint">/100</span>
          </td>
        </tr>
      </tbody>
    </table>
  );
}
