/**
 * Errores que llegan a la interfaz (D-A)
 * ======================================
 *
 * Rust serializa cada fallo de un comando como `{ code, detail }`: `code` es
 * estable y se traduce (`t.errors[code]`), `detail` es técnico y solo se
 * enseña plegado. Esta función normaliza cualquier cosa que llegue a un
 * `catch` o a `query.error` —ese objeto, un `Error` de JavaScript o un texto
 * suelto— a esa misma forma, para que ninguna vista pinte un error crudo.
 */

export interface AppError {
  code: string;
  detail: string;
}

/** Código de un fallo sin código conocido. */
export const UNKNOWN_ERROR = "unknown";

export function comoError(valor: unknown): AppError {
  if (valor && typeof valor === "object" && "code" in valor) {
    const { code, detail } = valor as { code: unknown; detail?: unknown };
    if (typeof code === "string") {
      return { code, detail: typeof detail === "string" ? detail : "" };
    }
  }
  if (valor instanceof Error) return { code: UNKNOWN_ERROR, detail: valor.message };
  return { code: UNKNOWN_ERROR, detail: valor == null ? "" : String(valor) };
}
