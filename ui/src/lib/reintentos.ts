/**
 * Reintentos de las consultas mientras el motor arranca
 * =====================================================
 *
 * La aplicación pinta sus vistas antes de que el motor Python conteste: el
 * arranque puede tardar hasta 30 s (60 sondeos de 500 ms en sidecar.rs). Una
 * consulta que llega antes recibe `sidecar_unreachable` (conexión rechazada)
 * y, con un único reintento a 1 s, la vista se quedaba vacía aunque el motor
 * contestara un momento después. Ese código se reintenta con espera creciente
 * hasta cubrir la ventana de arranque; los demás errores conservan su número
 * de reintentos, para no esconder fallos reales. `sidecar_timeout` no entra:
 * un motor que contesta tarde ya está en marcha.
 *
 * Importa con ruta relativa y extensión para poder probarse con `node --test`.
 */
import { comoError } from "./errors.ts";

/** Lo que puede tardar el motor en contestar tras lanzarse (sidecar.rs). */
export const VENTANA_DE_ARRANQUE_MS = 30_000;

const MOTOR_AUSENTE = "sidecar_unreachable";

/** 0,5 s, 1 s, 2 s, 4 s y después cada 5 s. */
export function esperaDeReintento(fallos: number): number {
  return Math.min(500 * 2 ** fallos, 5_000);
}

/** Reintentos necesarios para que las esperas sumen la ventana de arranque. */
const REINTENTOS_DE_ARRANQUE = (() => {
  let total = 0;
  let reintentos = 0;
  while (total < VENTANA_DE_ARRANQUE_MS) {
    total += esperaDeReintento(reintentos);
    reintentos += 1;
  }
  return reintentos;
})();

/** Política `retry` de TanStack Query: `otros` reintentos para lo que no es arranque. */
export function reintentarMientrasArranca(otros: number) {
  return (fallos: number, error: unknown): boolean =>
    comoError(error).code === MOTOR_AUSENTE ? fallos < REINTENTOS_DE_ARRANQUE : fallos < otros;
}
