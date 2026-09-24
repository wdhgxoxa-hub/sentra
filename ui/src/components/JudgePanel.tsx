import { CheckCircle2, Gavel, XCircle } from "lucide-react";

import { DocumentActions } from "@/components/DocumentActions";
import { ErrorNotice } from "@/components/ErrorNotice";
import { EvidenceAttributionLine } from "@/components/EvidenceAttributionLine";
import { comoError } from "@/lib/errors";
import { useJudgeTop } from "@/lib/queries";
import { useMultiscanStore } from "@/stores/multiscanStore";
import { useT } from "@/stores/settingsStore";
import type { JudgeVerdict, JudgeVersions, NicheVerdict, SourceCard } from "@/types/radar";

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
  if (etiquetador !== actuales.labeler) antiguas.push(etiquetador ?? t.judge.unknownLabeler);
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
  const abogado = v.advocate;
  const antiguas = versionesAntiguas(v, actuales, t);
  return (
    <article className="rounded-card border border-border bg-surface p-4">
      <header className="flex flex-wrap items-center gap-3">
        <span className={`rounded-lg border-2 px-3 py-1 text-base font-bold ${VERDICT_COLOR[v.verdict]}`}>
          {t.judge.verdict[v.verdict]}
        </span>
        <span className="text-sm font-semibold">{v.keywords.slice(0, 3).join(" · ") || v.clusterKey}</span>
        <span className="ml-auto text-xs text-ink-soft">
          {t.judge.score.replace("{score}", v.score.toFixed(1))}
        </span>
      </header>
      {antiguas.length > 0 && (
        <p className="mt-1 text-[11px] text-warn">
          {t.judge.oldVersions.replace("{versions}", antiguas.join(", "))}
        </p>
      )}
      <p className="mt-1 text-[11px] text-ink-faint">
        {t.judge.rule.replace("{rule}", v.rule)}
        {v.missing.length > 0 && ` · ${t.judge.missing.replace("{gates}", v.missing.join(", "))}`}
      </p>

      <section className="mt-3">
        <h4 className="mb-1 text-xs font-semibold">{t.judge.corroboration}</h4>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(v.corroboration).map(([fuente, n]) => (
            <span key={fuente} className="rounded-full border border-border px-2 py-0.5 text-[11px]">
              {nombre(fuente)} · {n}
            </span>
          ))}
        </div>
      </section>

      <section className="mt-3">
        <h4 className="mb-1 text-xs font-semibold">{t.judge.gates}</h4>
        <ul className="grid gap-1 sm:grid-cols-2">
          {v.gates.map((g) => (
            <li key={g.gate} className="flex items-start gap-1.5 text-[11px]">
              {g.passed ? (
                <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-ok" aria-label="ok" />
              ) : (
                <XCircle className="mt-0.5 size-3.5 shrink-0 text-danger" aria-label="falla" />
              )}
              <span>
                <span className="font-medium">{g.gate}</span>{" "}
                {t.judge.gateNames[g.gate as keyof T["judge"]["gateNames"]] ?? g.gate}
                <span className="block text-ink-faint">
                  {t.judge.valueVsThreshold
                    .replace("{value}", cifra(g.value))
                    .replace("{threshold}", cifra(g.threshold))}
                  {" · "}
                  {t.judge.evidenceCount.replace("{n}", String(g.evidenceIds.length))}
                </span>
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-3">
        <h4 className="mb-1 text-xs font-semibold">{t.judge.dimensions}</h4>
        <ul className="grid gap-0.5 text-[11px] text-ink-soft sm:grid-cols-2">
          {v.dimensions.map((d) => (
            <li key={d.name}>
              {t.judge.dimensionNames[d.name as keyof T["judge"]["dimensionNames"]] ?? d.name}:{" "}
              {d.note === "undetermined"
                ? t.judge.undetermined
                : d.note === "sin_datos"
                  ? // D-M9: el hueco sin menciones es un valor neutro, nunca una cifra medida.
                    d.name === "hueco"
                    ? t.judge.noCompetitionData
                    : t.judge.noData
                  : `${d.value === null ? "—" : cifra(d.value)} (${((d.normalized ?? 0) * 100).toFixed(0)} %)`}
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-3">
        <h4 className="mb-1 flex items-center gap-1.5 text-xs font-semibold">
          <Gavel className="size-3.5" aria-hidden="true" />
          {t.judge.advocate}
        </h4>
        {abogado.reason?.startsWith("advocate_unavailable") ? (
          <p className="text-xs text-warn">{t.judge.advocateUnavailable}</p>
        ) : abogado.downgraded && abogado.reason ? (
          <p className="text-xs text-warn">{t.judge.advocateDowngraded.replace("{reason}", abogado.reason)}</p>
        ) : null}
        {abogado.arguments.length === 0 && !abogado.downgraded && (
          <p className="text-xs text-ink-faint">{t.judge.advocateNoArguments}</p>
        )}
        <ul className="mt-1 flex flex-col gap-1">
          {abogado.arguments.map((a, n) => (
            <li key={n} className="text-xs">
              <span className="font-medium">{t.judge.severity[a.severity]}:</span> {a.claim}
              <span className="text-ink-faint"> ({a.evidenceIds.join(", ")})</span>
            </li>
          ))}
        </ul>
        {abogado.discarded.length > 0 && (
          <p className="mt-1 text-[11px] text-ink-faint">
            {t.judge.advocateDiscarded.replace("{n}", String(abogado.discarded.length))}
          </p>
        )}
      </section>

      <details className="mt-3">
        <summary className="cursor-pointer text-xs font-semibold">
          {t.judge.evidence} ({v.evidence.length})
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

      <DocumentActions v={v} />
    </article>
  );
}

/**
 * Panel del juez: Top 6 por veredicto (CONSTRUIR primero, sin rellenar),
 * con compuertas, corroboración, dimensiones, abogado del diablo y la
 * evidencia siempre atribuida (R5, D-SE3).
 */
export function JudgePanel({ cards }: { cards: SourceCard[] }) {
  const t = useT();
  const top = useJudgeTop(null);
  const juez = useMultiscanStore((s) => s.scan.judge);
  const nombre = (id: string) => cards.find((c) => c.source === id)?.displayName ?? id;

  return (
    <section className="flex flex-col gap-3">
      <header>
        <h3 className="text-sm font-semibold">{t.judge.title}</h3>
        <p className="mt-0.5 text-xs text-ink-soft">{t.judge.subtitle}</p>
      </header>

      {juez.status === "running" && <p className="text-xs text-ink-faint">{t.judge.judging}</p>}
      {juez.status === "error" && juez.error && (
        <ErrorNotice code={juez.error.code} detail={juez.error.detail} title={t.judge.judgeFailed} />
      )}
      {juez.status === "done" && juez.summary && (
        <p className="text-xs text-ink-soft">
          {t.judge.judgeSummary
            .replace("{kept}", String(juez.summary.kept))
            .replace("{items}", String(juez.summary.items))
            .replace("{labeled}", String(juez.summary.labeled))
            .replace("{clusters}", String(juez.summary.clusters))}
          {juez.summary.llm.model === null && <span className="block text-warn">{t.judge.noLlm}</span>}
        </p>
      )}
      {/* AUD-051: el motivo por el que el juez corrió sin Gemini, traducido. */}
      {juez.status === "done" && juez.summary?.llm.unavailable && (
        <ErrorNotice code={juez.summary.llm.unavailable} detail={juez.summary.llm.unavailable} tone="warn" />
      )}

      {top.isPending && <p className="text-sm text-ink-faint">{t.judge.loading}</p>}
      {top.isError && <ErrorNotice {...comoError(top.error)} title={t.judge.unreachable} />}
      {top.data && top.data.verdicts.length === 0 && (
        <p className="text-sm text-ink-faint">{top.data.reason ?? t.judge.empty}</p>
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
  );
}
