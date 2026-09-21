import {
  Check,
  Download,
  Filter,
  Brain,
  Database,
  Scale,
  Layers,
} from "lucide-react";

import { Explain } from "@/components/Explain";
import { useT } from "@/stores/settingsStore";
import { PIPELINE_NODES, type PipelineNode } from "@/types/radar";

const ICONS: Record<PipelineNode, typeof Download> = {
  fetch: Download,
  filter: Filter,
  intelligence: Brain,
  storage: Database,
  quality_gate: Scale,
  aggregate: Layers,
};

type NodeState = "pending" | "active" | "done";

/**
 * Los seis nodos del motor, encadenados.
 *
 * Enseñar el recorrido convierte una espera opaca en algo legible: se ve
 * que descargar fue instantáneo y que el análisis es lo que tarda. Cada
 * nodo lleva su explicación, porque «quality_gate» no significa nada para
 * quien no escribió el código.
 */
export function PipelineGraph({
  completed,
  current,
  compact = false,
}: {
  completed: PipelineNode[];
  current: PipelineNode | null;
  compact?: boolean;
}) {
  const t = useT();

  const stateOf = (node: PipelineNode): NodeState => {
    if (current === node) return "active";
    return completed.includes(node) ? "done" : "pending";
  };

  return (
    <ol className="flex flex-wrap items-center gap-1">
      {PIPELINE_NODES.map((node, index) => {
        const state = stateOf(node);
        const Icon = ICONS[node];

        const ring =
          state === "active"
            ? "border-accent bg-accent-soft text-accent"
            : state === "done"
              ? "border-ok/40 bg-ok/10 text-ok"
              : "border-border bg-surface-2 text-ink-faint";

        return (
          <li key={node} className="flex items-center gap-1">
            <div
              className={`flex items-center gap-1.5 rounded-lg border px-2 py-1 transition-colors duration-300 ${ring}`}
              title={t.pipeline.nodeHints[node]}
            >
              <span className="relative flex items-center">
                {state === "done" ? (
                  <Check className="size-3.5" aria-hidden="true" />
                ) : (
                  <Icon
                    className={`size-3.5 ${state === "active" ? "pulse-dot" : ""}`}
                    aria-hidden="true"
                  />
                )}
              </span>
              {!compact && (
                <span className="text-[11px] font-medium">
                  {t.pipeline.nodes[node]}
                </span>
              )}
              <span className="sr-only">
                {state === "done" ? "✓" : state === "active" ? "…" : ""}
              </span>
            </div>

            {index < PIPELINE_NODES.length - 1 && (
              <span
                className={`h-px w-2 transition-colors duration-300 ${
                  completed.includes(node)
                    ? "bg-ok/40"
                    : "bg-border"
                }`}
                aria-hidden="true"
              />
            )}
          </li>
        );
      })}

      {!compact && (
        <li className="ml-1">
          <Explain
            title={t.explain.cluster.title}
            body={t.explain.cluster.body}
          />
        </li>
      )}
    </ol>
  );
}
