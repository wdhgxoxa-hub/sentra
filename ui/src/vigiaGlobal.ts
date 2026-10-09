/**
 * Instala el vigía de errores en la ventana (src/lib/vigia.ts). Es la primera
 * importación de main.tsx: así ve también lo que falle al cargar la app.
 */
import { type ErroresVistos, vigilarErrores } from "@/lib/vigia";

declare global {
  interface Window {
    __sentraErrores?: ErroresVistos;
  }
}

window.__sentraErrores = vigilarErrores(window);
