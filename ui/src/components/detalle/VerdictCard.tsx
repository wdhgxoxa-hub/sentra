/**
 * Detalle técnico de un veredicto (compuertas, dimensiones, abogado del
 * diablo, evidencia). Solo se pinta dentro de «Ver detalle» (P1): fuera de
 * ahí la ficha del nicho lo cuenta en lenguaje llano.
 */

import { CheckCircle2, Gavel, MinusCircle, XCircle } from "lucide-react";

import { EvidenceAttributionLine } from "@/components/EvidenceAttributionLine";
import { nombreDelGrupo, puntuacionDelGrupo } from "@/lib/veredicto";
import { useSettingsStore, useT } from "@/stores/settingsStore";
import type { JudgeVerdict, JudgeVersions, NicheVerdict } from "@/types/radar";

export const VERDICT_COLOR: Record<NicheVerdict, string> = {
  CONSTRUIR: "border-ok text-ok",
  "INVESTIGAR MÁS": "border-warn text-warn",
  DESCARTAR: "border-danger text-danger",
};

type T = ReturnType<typeof useT>;

function cifra(valor: number): string {
  return Number.isInteger(valor) ? String(valor) : valor.toFixed(2);
}

/** B4: las versiones con las que se produjo el veredicto que no son las actuales. */
export function versionesAntiguas(v: JudgeVerdict, actuales: JudgeVersions, t: T): string[] {
  const antiguas: string[] = [];
  const etiquetador = v.labelerVersion?.split("/")[0] ?? null;
  if (etiquetador !== actuales.labeler) antiguas.push(etiquetador ?? t.detalle.unknownLabeler);
  if (v.clusteringVersion !== actuales.clustering) antiguas.push(v.clusteringVersion);
  if (v.weightsVersion !== actuales.weights) antiguas.push(v.weightsVersion);
  return antiguas;
}

export function VerdictCard({
  v,
  t,
  nombre,
  actuales,
}: {
  v: JudgeVerdict;
  t: T;
  nombre: (id: string) => string;
  actuales: JudgeVersions;
}) {
  const idioma = useSettingsStore((s) => s.language);
  const abogado = v.advocate;
  const antiguas = versionesAntiguas(v, actuales, t);
  return (
    <article className="rounded-card border border-border bg-surface p-4">
      <header className="flex flex-wrap items-center gap-3">
        <span className={`rounded-lg border-2 px-3 py-1 text-base font-bold ${VERDICT_COLOR[v.verdict]}`}>
          {t.detalle.verdict[v.verdict]}
        </span>
        <span className="text-sm font-semibold">{nombreDelGrupo(v, t.detalle.noCommonProblem, idioma)}</span>
        {puntuacionDelGrupo(v, t.detalle.score) && (
          <span className="ml-auto text-xs text-ink-soft">{puntuacionDelGrupo(v, t.detalle.score)}</span>
        )}
      </header>
      {antiguas.length > 0 && (
        <p className="mt-1 text-[11px] text-warn">
          {t.detalle.oldVersions.replace("{versions}", antiguas.join(", "))}
        </p>
      )}
      <p className="mt-1 text-[11px] text-ink-faint">
        {t.detalle.rule.replace("{rule}", v.rule)}
        {v.missing.length > 0 && ` · ${t.detalle.missing.replace("{gates}", v.missing.join(", "))}`}
      </p>

      <section className="mt-3">
        <h4 className="mb-1 text-xs font-semibold">{t.detalle.corroboration}</h4>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(v.corroboration).map(([fuente, n]) => (
            <span key={fuente} className="rounded-full border border-border px-2 py-0.5 text-[11px]">
              {nombre(fuente)} · {n}
            </span>
          ))}
        </div>
      </section>

      <section className="mt-3">
        <h4 className="mb-1 text-xs font-semibold">{t.detalle.gates}</h4>
        <ul className="grid gap-1 sm:grid-cols-2">
          {v.gates.map((g) => (
            <li key={g.gate} className="flex items-start gap-1.5 text-[11px]">
              {/* AUD2-005: sin nada que medir no hay ✓; se dice que no se midió. */}
              {!g.measured ? (
                <MinusCircle className="mt-0.5 size-3.5 shrink-0 text-ink-faint" aria-label={t.detalle.notMeasured} />
              ) : g.passed ? (
                <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-ok" aria-label="ok" />
              ) : (
                <XCircle className="mt-0.5 size-3.5 shrink-0 text-danger" aria-label="falla" />
              )}
              <span>
                <span className="font-medium">{g.gate}</span>{" "}
                {(t.detalle.gateNames[g.gate as keyof T["detalle"]["gateNames"]] ?? g.gate).replace(
                  "{n}",
                  cifra(g.threshold),
                )}
                <span className="block text-ink-faint">
                  {!g.measured && `${t.detalle.notMeasured} · `}
                  {t.detalle.valueVsThreshold
                    .replace("{value}", cifra(g.value))
                    .replace("{threshold}", cifra(g.threshold))}
                  {" · "}
                  {g.evidenceIds.length === 1
                    ? t.detalle.evidenceCountOne
                    : t.detalle.evidenceCount.replace("{n}", String(g.evidenceIds.length))}
                </span>
                {g.note && <span className="block text-ink-faint">{g.note}</span>}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-3">
        <h4 className="mb-1 text-xs font-semibold">{t.detalle.dimensions}</h4>
        <ul className="grid gap-0.5 text-[11px] text-ink-soft sm:grid-cols-2">
          {v.dimensions.map((d) => (
            <li key={d.name}>
              {t.detalle.dimensionNames[d.name as keyof T["detalle"]["dimensionNames"]] ?? d.name}:{" "}
              {d.note === "undetermined"
                ? t.detalle.undetermined
                : d.name === "tendencia" && d.value !== null
                  ? // Crecimiento relativo: -1 es «cae un 100 %», no «-1 (0 %)».
                    t.detalle.trend.replace("{pct}", `${d.value > 0 ? "+" : ""}${Math.round(d.value * 100)} %`)
                : d.note === "sin_datos"
                  ? // D-M9: el hueco sin menciones es un valor neutro, nunca una cifra medida.
                    d.name === "hueco"
                    ? t.detalle.noCompetitionData
                    : t.detalle.noData
                  : `${d.value === null ? "—" : cifra(d.value)} (${((d.normalized ?? 0) * 100).toFixed(0)} %)`}
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-3">
        <h4 className="mb-1 flex items-center gap-1.5 text-xs font-semibold">
          <Gavel className="size-3.5" aria-hidden="true" />
          {t.detalle.advocate}
        </h4>
        {abogado.reason?.startsWith("advocate_unavailable") ? (
          <p className="text-xs text-warn">{t.detalle.advocateUnavailable}</p>
        ) : abogado.downgraded && abogado.reason ? (
          <p className="text-xs text-warn">{t.detalle.advocateDowngraded.replace("{reason}", abogado.reason)}</p>
        ) : null}
        {abogado.arguments.length === 0 && !abogado.downgraded && (
          <p className="text-xs text-ink-faint">{t.detalle.advocateNoArguments}</p>
        )}
        <ul className="mt-1 flex flex-col gap-1">
          {abogado.arguments.map((a, n) => (
            <li key={n} className="text-xs">
              <span className="font-medium">{t.detalle.severity[a.severity]}:</span> {a.claim}
              <span className="text-ink-faint"> ({a.evidenceIds.join(", ")})</span>
            </li>
          ))}
        </ul>
        {abogado.discarded.length > 0 && (
          <p className="mt-1 text-[11px] text-ink-faint">
            {t.detalle.advocateDiscarded.replace("{n}", String(abogado.discarded.length))}
          </p>
        )}
      </section>

      <details className="mt-3">
        <summary className="cursor-pointer text-xs font-semibold">
          {t.detalle.evidence} ({v.evidence.length})
        </summary>
        <ul className="mt-2 flex flex-col gap-2">
          {v.evidence.map((e) => (
            <li key={e.id} className="rounded-lg border border-border p-2">
              <p className="text-xs">{e.excerpt}</p>
              {/* AUD-045: cada pieza con su fecha y su enlace, no solo el texto. */}
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <time dateTime={e.createdAt} className="text-[11px] text-ink-faint">
                  {new Date(e.createdAt).toLocaleDateString()}
                </time>
                <EvidenceAttributionLine attribution={e.attribution} />
              </div>
            </li>
          ))}
        </ul>
      </details>

    </article>
  );
}
