import type { ReactNode } from "react";

export type Tono = "danger" | "warn";

const TONOS: Record<Tono, string> = {
  danger: "text-danger",
  warn: "text-warn",
};

/**
 * La misma presentación con los textos ya resueltos.
 *
 * La usa `ErrorBoundary`, que no puede depender del store de idioma: si lo
 * que falla es ese store, su aviso caería con el mismo error. Por eso vive
 * en su propio módulo, que no lo importa.
 */
export function ErrorNoticeView({
  title,
  message,
  detail,
  detailsLabel,
  tone = "danger",
  children,
}: {
  title?: string;
  message: string;
  detail: string;
  detailsLabel: string;
  tone?: Tono;
  children?: ReactNode;
}) {
  return (
    <div role="alert" className={`text-xs leading-relaxed ${TONOS[tone]}`}>
      {title && <p className="font-medium">{title}</p>}
      <p>{message}</p>
      {children}
      {detail && (
        <details className="mt-1 text-ink-faint">
          <summary className="cursor-pointer">{detailsLabel}</summary>
          <pre className="mt-1 max-h-48 overflow-auto rounded-lg bg-surface-2 p-2 font-mono text-xs whitespace-pre-wrap break-all">
            {detail}
          </pre>
        </details>
      )}
    </div>
  );
}
