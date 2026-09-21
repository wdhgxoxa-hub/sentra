import { Component, type ErrorInfo, type ReactNode } from "react";

interface Textos {
  title: string;
  hint: string;
  retry: string;
  details: string;
}

interface Props {
  children: ReactNode;
  textos: Textos;
  /** Al cambiar, se vuelve a intentar pintar: navegar ya es un reintento. */
  resetKey?: unknown;
}

interface State {
  error: Error | null;
}

/**
 * Red de seguridad de render.
 *
 * React desmonta el árbol entero cuando un componente lanza durante el
 * render, y el resultado es una ventana en blanco sin ninguna pista. Aquí se
 * detiene la caída: se enseña qué falló y se puede seguir usando el resto de
 * la aplicación.
 *
 * Los textos llegan como prop y no desde el store de idioma a propósito: si
 * lo que falla es justamente ese store, un fallback que dependiera de él
 * caería con el mismo error y volveríamos a la pantalla vacía.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Queda en la consola del webview con el árbol de componentes, que es lo
    // que hace falta para localizarlo.
    console.error("[radar] vista caída:", error, info.componentStack);
  }

  componentDidUpdate(prev: Props): void {
    if (this.state.error && prev.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    const { textos } = this.props;

    return (
      <div
        role="alert"
        className="mx-auto flex max-w-xl flex-col items-start gap-3 rounded-card border border-danger/30 bg-surface p-6"
      >
        <h2 className="text-base font-semibold text-danger">{textos.title}</h2>
        <p className="text-sm leading-relaxed text-ink-soft">{textos.hint}</p>

        <details className="w-full">
          <summary className="cursor-pointer text-xs text-ink-faint">
            {textos.details}
          </summary>
          <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-surface-2 p-3 font-mono text-[11px] leading-relaxed whitespace-pre-wrap text-ink-soft">
            {error.message || String(error)}
          </pre>
        </details>

        <button
          type="button"
          onClick={() => this.setState({ error: null })}
          className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
        >
          {textos.retry}
        </button>
      </div>
    );
  }
}
