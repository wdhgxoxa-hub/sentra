/**
 * Estado de una fuente en una frase (Fase 2, P1)
 * ==============================================
 *
 * La fila de Fuentes dice en palabras si la fuente entra en los escaneos y,
 * si no, por qué. `clave` es la de `t.sources.fila` y `t.sources.filaExplica`.
 */

import type { SourceCard } from "@/types/radar";

export type EstadoDeFila = "lista" | "sin_probar" | "fallo" | "sin_conectar" | "apagada" | "fuera_comercial";
export type TonoDeFila = "bien" | "aviso" | "mal" | "neutro";

export function estadoDeLaFila(
  card: Pick<SourceCard, "status" | "active" | "disabled" | "excludedByCommercialMode">,
): { clave: EstadoDeFila; tono: TonoDeFila } {
  if (card.disabled || card.status === "deshabilitada_por_usuario") return { clave: "apagada", tono: "neutro" };
  if (card.excludedByCommercialMode) return { clave: "fuera_comercial", tono: "neutro" };
  if (card.status === "error") return { clave: "fallo", tono: "mal" };
  if (card.status === "no_configurada") return { clave: "sin_conectar", tono: "neutro" };
  if (card.status === "configurada_sin_verificar") return { clave: "sin_probar", tono: "aviso" };
  return { clave: "lista", tono: "bien" };
}
