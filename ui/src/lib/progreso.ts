/**
 * Progreso por fuente en palabras de todos los días (Fase 2, P1)
 * ==============================================================
 *
 * El estado de una fuente durante el escaneo, traducido a lo que entiende
 * cualquiera: un tono (color), un icono, una palabra corta y una frase. La
 * palabra y la frase son claves de i18n (`t.progreso.palabra`,
 * `t.progreso.frase`). Nada depende solo del color. El código técnico, si lo
 * hay, se guarda en `codigo` para «Ver detalle» y nunca se pinta suelto.
 */

import type { SourceScanSummary } from "@/types/radar";

export type TonoDeFuente = "en_curso" | "bien" | "aviso" | "mal" | "neutro";
export type IconoDeFuente = "reloj" | "hecho" | "alerta" | "cruz" | "pausa";
export type PalabraDeFuente = "buscando" | "lista" | "parcial" | "fallo" | "cancelada" | "no_se_usa";
export type FraseDeFuente =
  | "buscando"
  | "lista"
  | "cancelada"
  | "tope_propio"
  | "parada_antes"
  | "pidio_esperar"
  | "falta_cuenta"
  | "clave_no_funciona"
  | "rechazo"
  | "no_respondio"
  | "pendiente_aprobacion"
  | "inesperado";

export interface EstadoDeFuente {
  tono: TonoDeFuente;
  icono: IconoDeFuente;
  palabra: PalabraDeFuente;
  frase: FraseDeFuente;
  items: number;
  /** El código del motor, para «Ver detalle»; null si no hay. */
  codigo: string | null;
}

const ICONO: Record<TonoDeFuente, IconoDeFuente> = {
  en_curso: "reloj",
  bien: "hecho",
  aviso: "alerta",
  mal: "cruz",
  neutro: "pausa",
};

/** Fallos conocidos: tono, palabra y frase. */
const FALLOS: Record<string, [TonoDeFuente, PalabraDeFuente, FraseDeFuente]> = {
  source_rate_limited: ["aviso", "parcial", "pidio_esperar"],
  source_credentials_missing: ["mal", "fallo", "falta_cuenta"],
  source_auth_failed: ["mal", "fallo", "clave_no_funciona"],
  source_forbidden: ["mal", "fallo", "rechazo"],
  source_not_found: ["mal", "fallo", "rechazo"],
  source_unavailable: ["mal", "fallo", "no_respondio"],
  source_error: ["mal", "fallo", "no_respondio"],
  internal_error: ["mal", "fallo", "no_respondio"],
  source_pending_approval: ["neutro", "no_se_usa", "pendiente_aprobacion"],
};

function estado(
  [tono, palabra, frase]: [TonoDeFuente, PalabraDeFuente, FraseDeFuente],
  items: number,
  codigo: string | null,
): EstadoDeFuente {
  return { tono, icono: ICONO[tono], palabra, frase, items, codigo };
}

export function estadoDeFuente(s: SourceScanSummary): EstadoDeFuente {
  if (s.status === "running") return estado(["en_curso", "buscando", "buscando"], s.items, null);
  if (s.status === "failed") {
    const codigo = s.errorCode ?? "source_error";
    return estado(FALLOS[codigo] ?? ["mal", "fallo", "inesperado"], s.items, codigo);
  }
  if (s.stopReason === null) return estado(["bien", "lista", "lista"], s.items, null);
  if (s.stopReason === "cancelled") return estado(["neutro", "cancelada", "cancelada"], s.items, s.stopReason);
  if (s.stopReason === "source_budget_exhausted") {
    return estado(["aviso", "parcial", "tope_propio"], s.items, s.stopReason);
  }
  return estado(["aviso", "parcial", "parada_antes"], s.items, s.stopReason);
}
