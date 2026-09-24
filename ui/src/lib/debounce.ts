import { useEffect, useState } from "react";

/**
 * El valor, pero solo cuando lleva `ms` sin cambiar (AUD-054).
 *
 * Para lo que cuesta pedir: la búsqueda carga el modelo e5 y consulta
 * PostgreSQL, y lanzarla a cada tecla era una petición por letra.
 */
export function useDebouncedValue<T>(valor: T, ms: number): T {
  const [estable, setEstable] = useState(valor);
  useEffect(() => {
    const temporizador = window.setTimeout(() => setEstable(valor), ms);
    return () => window.clearTimeout(temporizador);
  }, [valor, ms]);
  return estable;
}
