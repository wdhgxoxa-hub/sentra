import { useState } from "react";

import { useT } from "@/stores/settingsStore";
import { direccionVisible } from "@/lib/direccion";

/**
 * La dirección del original (D-M12, Fase 3): se ve acortada, sin la cuenta
 * del autor (R9), y «Copiar dirección» copia la completa (R5). La completa
 * solo va en el destino del botón, nunca como texto. La ventana no abre
 * enlaces externos: la persona la pega en su navegador.
 */
export function DireccionDelOriginal({ url, className = "" }: { url: string; className?: string }) {
  const t = useT();
  const [copiada, setCopiada] = useState(false);
  const copiar = () => {
    void navigator.clipboard.writeText(url).then(() => setCopiada(true), () => setCopiada(false));
  };
  return (
    <span className={`inline-flex flex-wrap items-center gap-1.5 ${className}`}>
      <span className="select-all" data-ajeno="">{direccionVisible(url)}</span>
      <button
        type="button"
        onClick={copiar}
        data-destino={url}
        className="rounded border border-border px-1.5 py-0.5 text-xs text-ink-soft hover:text-ink"
      >
        {copiada ? t.comun.direccionCopiada : t.comun.copiarDireccion}
      </button>
    </span>
  );
}
