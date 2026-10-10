import { Bot, Eye, X } from "lucide-react";

import { BotonSecundario } from "@/components/comunes/Comunes";
import { asistenteDesdePropuesta } from "@/lib/propuestas";
import { useDiscardScanRequest, useScanRequests } from "@/lib/queries";
import { useAsistenteStore } from "@/stores/asistenteStore";
import { useMultiscanStore } from "@/stores/multiscanStore";
import { useT } from "@/stores/settingsStore";

/**
 * Los escaneos que propone Claude Desktop (servidor MCP). Aquí no se lanza
 * nada: «Revisar» lleva la propuesta al paso de revisar, con lo que costará,
 * y solo «Escanear» la lanza. Los botones son secundarios: la acción
 * principal de la pantalla sigue siendo la del asistente.
 */
export function PropuestasDeClaude() {
  const t = useT();
  const propuestas = useScanRequests();
  const descartar = useDiscardScanRequest();
  const a = useAsistenteStore();
  const resetEscaneo = useMultiscanStore((s) => s.reset);

  const visibles = (propuestas.data?.requests ?? []).filter((p) => p.id !== a.propuestaId);
  if (visibles.length === 0) return null;

  return (
    <section className="flex flex-col gap-3" aria-label={t.nuevoEscaneo.propuestas.titulo}>
      {visibles.map((p) => (
        <article key={p.id} className="flex flex-col gap-3 rounded-card border border-accent/40 bg-surface p-5 shadow-card">
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <Bot className="size-5 text-accent" aria-hidden="true" />
            {t.nuevoEscaneo.propuestas.titulo}
          </h2>
          <p className="text-[15px] font-medium" data-ajeno>
            {p.profile.discovery ? t.nuevoEscaneo.propuestas.sinTema : p.profile.topic || p.profile.name}
          </p>
          {p.reason && (
            <p className="text-sm text-ink-soft">
              <span className="font-medium text-ink">{t.nuevoEscaneo.propuestas.motivo}: </span>
              <span data-ajeno>{p.reason}</span>
            </p>
          )}
          <div className="flex flex-wrap justify-end gap-2">
            <BotonSecundario onClick={() => descartar.mutate(p.id)} disabled={descartar.isPending}>
              <X className="size-4" aria-hidden="true" />
              {t.nuevoEscaneo.propuestas.descartar}
            </BotonSecundario>
            <BotonSecundario
              onClick={() => {
                resetEscaneo();
                a.reiniciar();
                a.set({ ...asistenteDesdePropuesta(p.profile), propuestaId: p.id, motivoDeClaude: p.reason });
              }}
            >
              <Eye className="size-4" aria-hidden="true" />
              {t.nuevoEscaneo.propuestas.revisar}
            </BotonSecundario>
          </div>
        </article>
      ))}
    </section>
  );
}
