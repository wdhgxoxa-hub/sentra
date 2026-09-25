import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";

import { BotonSecundario, VerDetalle } from "@/components/comunes/Comunes";
import { DocumentosDelNicho } from "@/components/nicho/DocumentosDelNicho";
import { porQueDelNicho, Veredicto } from "@/components/nicho/TarjetaDeNicho";
import type { Modo, NichoEnPantalla } from "@/modos/tipos";
import { useT } from "@/stores/settingsStore";

/**
 * Ficha de un nicho (Fase 2): qué es, por qué el juez decidió eso en una
 * frase llana, dossier y plan a la vista con su estado y su coste, y
 * algunas quejas con su enlace. Lo técnico, en «Ver detalle» (lo pone quien
 * conoce el modo). Genérica: sirve para cualquier modo.
 */
export function FichaDeNicho({
  nicho,
  modo,
  onVolver,
  detalle,
}: {
  nicho: NichoEnPantalla;
  modo: Modo;
  onVolver: () => void;
  detalle?: ReactNode;
}) {
  const t = useT();
  return (
    <div className="mx-auto flex max-w-[1080px] flex-col gap-6" data-pantalla="ficha" data-ficha={nicho.id}>
      <div>
        <BotonSecundario onClick={onVolver}>
          <ArrowLeft className="size-4" aria-hidden="true" />
          {t.nicho.volverAlRadar}
        </BotonSecundario>
      </div>
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Veredicto veredicto={nicho.veredicto} />
          <span className="text-sm text-ink-soft">{t.nicho.veredictoExplica[nicho.veredicto]}</span>
        </div>
        <h1 className="text-[24px] font-semibold" data-ajeno="">{nicho.nombre}</h1>
        {nicho.subnombre && <p className="text-[15px] text-ink-soft" data-ajeno="">{nicho.subnombre}</p>}
        <p className="text-sm text-ink-faint">{nicho.metricas.map((m) => modo.metrica(t, m)).join(" · ")}</p>
      </header>

      <DocumentosDelNicho nicho={nicho} />

      <section className="flex flex-col gap-3 rounded-card border border-border bg-surface p-6 shadow-card">
        <h2 className="text-base font-semibold">
          {t.nicho.porQueTitulo.replace("{veredicto}", t.nicho.veredicto[nicho.veredicto])}
        </h2>
        <p className="text-[15px]">{porQueDelNicho(t, nicho)}</p>
        {nicho.quejas.length > 0 && (
          <>
            <h3 className="mt-2 text-sm font-semibold">{t.nicho.quejas}</h3>
            <ul className="flex flex-col gap-2">
              {nicho.quejas.map((q, i) => (
                <li key={i} className="border-l-4 border-border-strong pl-3 text-sm text-ink-soft">
                  <span data-ajeno="">«{q.texto}»</span> · {q.fuente}
                  {/* La ventana no abre enlaces externos: la dirección, seleccionable. */}
                  {q.url && (
                    <span className="mt-1 block select-all break-all text-[13px] text-ink-faint" data-ajeno="">
                      {q.url}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      {detalle && <VerDetalle>{detalle}</VerDetalle>}
    </div>
  );
}
