import { HelpCircle } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { useT } from "@/stores/settingsStore";

/**
 * Explicación de una métrica, en lenguaje llano.
 *
 * El producto maneja conceptos que no son evidentes —JTBD, RRF, difusión—.
 * Poner la definición a un clic, junto al número, evita dos males: una
 * interfaz llena de párrafos que nadie lee, y una llena de siglas que nadie
 * entiende.
 *
 * Es un botón real y no un `title=`: los tooltips nativos no se abren con
 * teclado, tardan un segundo en aparecer y no se pueden leer con calma.
 */
export function Explain({
  title,
  body,
  align = "start",
}: {
  title: string;
  body: string;
  align?: "start" | "end";
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLSpanElement>(null);
  const panelId = useId();

  // Cerrar al pulsar fuera o con Escape: un panel que se queda abierto
  // tapando la tabla es peor que no tener explicación.
  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <span ref={containerRef} className="relative inline-flex align-middle">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        aria-label={`${t.common.whatIsThis}: ${title}`}
        className="inline-flex size-4 items-center justify-center rounded-full text-[--color-ink-faint] transition-colors hover:text-[--color-accent]"
      >
        <HelpCircle className="size-3.5" aria-hidden="true" />
      </button>

      {open && (
        <span
          id={panelId}
          role="note"
          className={`enter absolute top-6 z-50 w-72 rounded-[--radius-card] border border-[--color-border] bg-[--color-surface] p-3 text-left shadow-[--shadow-pop] ${
            align === "end" ? "right-0" : "left-0"
          }`}
        >
          <span className="block text-sm font-semibold">{title}</span>
          <span className="mt-1 block text-xs leading-relaxed text-[--color-ink-soft]">
            {body}
          </span>
        </span>
      )}
    </span>
  );
}
