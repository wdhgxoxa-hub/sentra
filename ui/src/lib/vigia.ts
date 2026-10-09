/**
 * Vigía de errores de la interfaz: excepciones sin capturar y violaciones de
 * CSP desde el arranque. El humo en Linux los lee en `window.__sentraErrores`
 * (WebKitWebDriver no da la consola, como sí hace WebView2 en Windows).
 */

export interface ErroresVistos {
  excepciones: string[];
  csp: number;
}

/** Cuántas excepciones se guardan: para el humo basta saber que hubo. */
const MAX_EXCEPCIONES = 50;

function describir(valor: unknown, alternativa: unknown): string {
  if (valor instanceof Error) return valor.stack ?? `${valor.name}: ${valor.message}`;
  return String(valor ?? alternativa ?? "error desconocido");
}

export function vigilarErrores(ventana: EventTarget): ErroresVistos {
  const vistos: ErroresVistos = { excepciones: [], csp: 0 };
  const apuntar = (texto: string) => {
    if (vistos.excepciones.length < MAX_EXCEPCIONES) vistos.excepciones.push(texto);
  };
  ventana.addEventListener("error", (e) => {
    const { error, message } = e as Event & { error?: unknown; message?: unknown };
    apuntar(describir(error, message));
  });
  ventana.addEventListener("unhandledrejection", (e) => {
    apuntar(describir((e as Event & { reason?: unknown }).reason, undefined));
  });
  ventana.addEventListener("securitypolicyviolation", () => {
    vistos.csp += 1;
  });
  return vistos;
}
