import { ErrorNotice } from "@/components/ErrorNotice";
import { comoError } from "@/lib/errors";
import { useJudgeTop } from "@/lib/queries";
import { useMultiscanStore } from "@/stores/multiscanStore";
import { useT } from "@/stores/settingsStore";
import { useUiStore } from "@/stores/uiStore";
import type { NicheVerdict } from "@/types/radar";

/**
 * Panel del juez en Fuentes: cómo fue el juicio tras el escaneo y un resumen
 * de los veredictos con enlace al Radar, que es el único sitio donde se ven
 * enteros (AUD2-008, DP6 A: antes se repetía aquí el Top completo).
 */
export function JudgePanel() {
  const t = useT();
  const top = useJudgeTop(null);
  const juez = useMultiscanStore((s) => s.scan.judge);
  const setView = useUiStore((s) => s.setView);
  const todos = [...(top.data?.verdicts ?? []), ...(top.data?.rest ?? [])];
  const cuantos = (veredicto: NicheVerdict) => String(todos.filter((v) => v.verdict === veredicto).length);

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
      {/* Fase 1, B4: un tope de Gemini cortó el juez; el texto dice cuál y dónde subirlo. */}
      {juez.status === "done" && juez.summary?.llm.stopReason && (
        <ErrorNotice
          code={juez.summary.llm.stopReason}
          detail={juez.summary.llm.stopReason}
          title={t.judge.stoppedByCap}
          tone="warn"
        />
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
          <p className="text-xs">
            {t.judge.summaryByVerdict
              .replace("{build}", cuantos("CONSTRUIR"))
              .replace("{research}", cuantos("INVESTIGAR MÁS"))
              .replace("{discard}", cuantos("DESCARTAR"))}
          </p>
          <button
            type="button"
            onClick={() => setView("radar")}
            className="self-start rounded-lg border border-border px-3 py-1.5 text-xs transition-colors hover:bg-surface-2"
          >
            {t.judge.seeInRadar}
          </button>
        </>
      )}
    </section>
  );
}
