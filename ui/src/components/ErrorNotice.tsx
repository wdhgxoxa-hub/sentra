import type { ReactNode } from "react";

import { ErrorNoticeView, type Tono } from "@/components/ErrorNoticeView";
import { UNKNOWN_ERROR, type AppError } from "@/lib/errors";
import { useT } from "@/stores/settingsStore";

/**
 * Aviso de error de toda la interfaz (D-A).
 *
 * Enseña el texto traducido del código y deja el detalle técnico plegado
 * bajo «Detalles técnicos»: quien usa la aplicación lee qué pasó, y quien
 * la depura tiene el mensaje original a un clic, pero nunca en primer plano.
 */
export function ErrorNotice({
  code,
  detail,
  title,
  tone = "danger",
  children,
}: AppError & { title?: string; tone?: Tono; children?: ReactNode }) {
  const t = useT();
  const mensajes = t.errors as Record<string, string>;
  return (
    <ErrorNoticeView
      title={title}
      message={mensajes[code] ?? mensajes[UNKNOWN_ERROR]}
      detail={detail}
      detailsLabel={t.common.technicalDetails}
      tone={tone}
    >
      {children}
    </ErrorNoticeView>
  );
}
