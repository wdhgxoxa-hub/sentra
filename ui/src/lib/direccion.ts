/**
 * La dirección del original tal como se ve (D-M12, Fase 3).
 *
 * Se guarda completa (R5: sin ella no se verifica la evidencia), pero la
 * cuenta del autor nunca se ve como texto (R9). La de Bluesky lleva el DID o
 * el @usuario tras `/profile/`: ese tramo, y cualquier otro que lleve un DID
 * o sea un @usuario, se ve como «…». La completa solo viaja como destino de
 * «Copiar dirección».
 */

/** Lleva un DID (did:plc:…, did:web:…, did:key:…) o es un @usuario: como `core/privacidad.py`. */
const CUENTA = /did:(?:plc|web|key):|^@./i;

export function direccionVisible(url: string): string {
  let partes: URL;
  try {
    partes = new URL(url);
  } catch {
    return url;
  }
  const tramos = partes.pathname.split("/");
  const esBluesky = partes.hostname === "bsky.app";
  const visibles = tramos.map((tramo, i) =>
    CUENTA.test(decodeURIComponent(tramo)) || (esBluesky && tramos[i - 1] === "profile" && tramo) ? "…" : tramo,
  );
  return `${partes.host}${visibles.join("/")}${partes.search}`;
}
