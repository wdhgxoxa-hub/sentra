import { AlertTriangle, Check, Copy, Loader2, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import bash from "highlight.js/lib/languages/bash";
import json from "highlight.js/lib/languages/json";
import python from "highlight.js/lib/languages/python";
import rust from "highlight.js/lib/languages/rust";
import sql from "highlight.js/lib/languages/sql";
import typescript from "highlight.js/lib/languages/typescript";
import yaml from "highlight.js/lib/languages/yaml";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";

import { ErrorNotice } from "@/components/ErrorNotice";
import { comoError } from "@/lib/errors";
import { ipc, onArchitectChunk } from "@/lib/ipc";
import { useSettings } from "@/lib/queries";
import { useArchitectStore } from "@/stores/architectStore";
import { useSettingsStore, useT } from "@/stores/settingsStore";
import type { ArchitectFailure } from "@/types/radar";

/** Texto original de un nodo del árbol de Markdown, sin las etiquetas del resaltado. */
function textoDe(nodo: unknown): string {
  const n = nodo as { value?: string; children?: unknown[] } | null | undefined;
  if (!n) return "";
  if (typeof n.value === "string") return n.value;
  return (n.children ?? []).map(textoDe).join("");
}

// Solo los lenguajes que salen en un plan de construccion. El paquete
// completo de highlight.js pesa mas que el resto de la aplicacion junta.
const LENGUAJES = { bash, json, python, rust, sql, typescript, yaml };

async function alPortapapeles(texto: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(texto);
    return true;
  } catch {
    return false;
  }
}

/**
 * Plan de construcción redactado por Gemini.
 *
 * El documento se pinta según llega y no al final: con un modelo de
 * razonamiento tarda minutos, y una pantalla quieta durante ese rato se lee
 * como una aplicación colgada.
 *
 * Va separado del PRD determinista a propósito. Aquel sale de la evidencia y
 * no inventa; este lo escribe un modelo generativo, y el aviso de abajo está
 * para que nadie confunda una propuesta con una medición.
 */
export function ArchitectPanel({ clusterKey }: { clusterKey: string }) {
  const t = useT();
  const language = useSettingsStore((state) => state.language);
  const settings = useSettings();

  const [texto, setTexto] = useState("");
  const [generando, setGenerando] = useState(false);
  // El fallo tipado llega por el canal antes de que el comando rechace; si
  // ya lo hay, el rechazo no lo pisa (AUD-020, D-A).
  const [fallo, setFallo] = useState<ArchitectFailure | null>(null);
  const [copiado, setCopiado] = useState<"si" | "no" | null>(null);
  const finDelTexto = useRef<HTMLDivElement | null>(null);

  const configurado = settings.data?.gemini?.configured ?? false;
  // El plan terminado se comparte con la exportación a PDF (AUD-008).
  const guardarPlan = useArchitectStore((state) => state.setPlan);

  // La suscripción vive mientras el panel está montado, no solo mientras
  // genera: los primeros trozos llegan antes de que un efecto disparado por
  // el clic alcance a registrarse, y se perderían.
  useEffect(() => {
    const unlisten = onArchitectChunk((chunk) => {
      if (chunk.clusterKey !== clusterKey) return;
      if (chunk.error) {
        setFallo(chunk.error);
        return;
      }
      if (chunk.done) return;
      setTexto((previo) => previo + chunk.text);
    });
    return () => {
      void unlisten.then((stop) => stop());
    };
  }, [clusterKey]);

  // Seguir el final mientras se escribe, como una consola.
  useEffect(() => {
    if (generando) finDelTexto.current?.scrollIntoView({ block: "end" });
  }, [texto, generando]);

  const generar = async () => {
    setTexto("");
    setFallo(null);
    setGenerando(true);
    try {
      const completo = await ipc.generateArchitecture(clusterKey, language);
      setTexto(completo);
      guardarPlan(clusterKey, completo);
    } catch (rechazo) {
      setFallo((previo) => previo ?? { ...comoError(rechazo), missing: [] });
    } finally {
      setGenerando(false);
    }
  };

  const copiar = async (contenido: string) => {
    setCopiado((await alPortapapeles(contenido)) ? "si" : "no");
    window.setTimeout(() => setCopiado(null), 2500);
  };

  return (
    <section className="rounded-card border border-border bg-surface">
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-5 py-3.5">
        <button
          type="button"
          onClick={generar}
          disabled={generando || !configurado}
          className="inline-flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-on-accent transition-colors hover:bg-accent-hover disabled:opacity-40"
        >
          {generando ? (
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          ) : (
            <Sparkles className="size-4" aria-hidden="true" />
          )}
          {texto && !generando ? t.architect.regenerate : t.architect.open}
        </button>

        {settings.data && !configurado && (
          <span className="text-xs text-warn">{t.settings.aiHint}</span>
        )}

        {texto && !generando && (
          <button
            type="button"
            onClick={() => copiar(texto)}
            className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-surface-2"
          >
            {copiado === "si" ? (
              <Check className="size-3.5 text-ok" aria-hidden="true" />
            ) : (
              <Copy className="size-3.5" aria-hidden="true" />
            )}
            {copiado === "si"
              ? t.architect.copied
              : copiado === "no"
                ? t.architect.copyFailed
                : t.architect.copy}
          </button>
        )}
      </div>

      <div className="px-5 py-5">
        {fallo && (
          <div className="mb-3">
            <ErrorNotice code={fallo.code} detail={fallo.detail} title={t.architect.error}>
              {fallo.missing.length > 0 && (
                <p className="mt-1">
                  {t.architect.missing}: {fallo.missing.join(", ")}
                </p>
              )}
              {texto && <p className="mt-1 text-warn">{t.architect.incomplete}</p>}
            </ErrorNotice>
          </div>
        )}

        {!texto && !generando && !fallo && (
          <p className="text-sm leading-relaxed text-ink-soft">
            {t.architect.empty}
          </p>
        )}

        {generando && !texto && (
          <p className="flex items-center gap-2 text-sm text-ink-faint">
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
            {t.architect.generating}
          </p>
        )}

        {texto && (
          <>
            <div className="markdown max-h-[32rem] overflow-auto pr-1">
              <Markdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[[rehypeHighlight, { languages: LENGUAJES }]]}
                components={{
                  pre({ children, node }) {
                    const codigo = textoDe(node);
                    return (
                      <div className="group/code relative">
                        <button
                          type="button"
                          onClick={() => copiar(codigo)}
                          className="absolute right-2 top-2 rounded-md border border-border bg-surface px-2 py-1 text-[11px] opacity-0 transition-opacity focus-visible:opacity-100 group-hover/code:opacity-100"
                        >
                          {t.architect.copyCode}
                        </button>
                        <pre>{children}</pre>
                      </div>
                    );
                  },
                }}
              >
                {texto}
              </Markdown>
              <div ref={finDelTexto} />
            </div>

            <p className="mt-3 flex items-start gap-1.5 border-t border-border pt-3 text-[11px] leading-relaxed text-warn">
              <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden="true" />
              {t.architect.warning}
            </p>
          </>
        )}
      </div>
    </section>
  );
}
