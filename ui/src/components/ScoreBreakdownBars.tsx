import { SCORE_WEIGHTS, type ScoreBreakdown } from "@/types/radar";

const ROWS: Array<{ key: keyof typeof SCORE_WEIGHTS; label: string }> = [
  { key: "spreadFactor", label: "Difusión" },
  { key: "frequencyFactor", label: "Frecuencia" },
  { key: "severityFactor", label: "Severidad" },
  { key: "recencyFactor", label: "Recencia" },
  { key: "paidSignalFactor", label: "Disposición a pagar" },
];

/**
 * El desglose se muestra como barras y no como un número suelto: un 73.5
 * no explica nada, mientras que "difusión al máximo, frecuencia baja" dice
 * que el problema está extendido pero aún no es recurrente.
 */
export function ScoreBreakdownBars({ breakdown }: { breakdown: ScoreBreakdown }) {
  return (
    <table className="w-full text-sm">
      <caption className="sr-only">Desglose de la puntuación</caption>
      <tbody>
        {ROWS.map(({ key, label }) => {
          const factor = breakdown[key];
          const points = factor * SCORE_WEIGHTS[key] * 100;
          return (
            <tr key={key}>
              <th scope="row" className="py-1 pr-3 text-left font-normal text-[--color-ink-muted]">
                {label}
              </th>
              <td className="w-full py-1">
                <div className="h-2 rounded-full bg-[--color-border-subtle]">
                  <div
                    className="h-2 rounded-full bg-[--color-urgency-high]"
                    style={{ width: `${Math.round(factor * 100)}%` }}
                  />
                </div>
              </td>
              <td className="py-1 pl-3 text-right font-mono tabular-nums">
                {points.toFixed(1)}
              </td>
            </tr>
          );
        })}
        <tr className="border-t border-[--color-border-subtle] font-semibold">
          <th scope="row" className="py-1 pr-3 text-left">Total</th>
          <td />
          <td className="py-1 pl-3 text-right font-mono tabular-nums">
            {breakdown.finalScore.toFixed(1)}
          </td>
        </tr>
      </tbody>
    </table>
  );
}
