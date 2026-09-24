# Spec: cerrar pendientes de SENTRA + Fase 4 (documentos)

Rama `feat/cierre-y-documentos` desde `main` 0e46f1c. El enunciado completo es
la misión pegada por el usuario el 2026-09-23; aquí quedan el objetivo, los
supuestos, las decisiones y los criterios de éxito verificables.

## Objetivo

1. Dejar SENTRA sin deuda conocida: fiabilidad del juez (truncado, pooling,
   calibración de la agrupación, versiones), una sola verdad en la interfaz,
   deuda residual y triaje AUD-032…AUD-071.
2. Fase 4: desde un veredicto, un dossier para decidir y un plan de
   construcción que un agente pueda ejecutar paso a paso sin preguntar.

## Decisiones

- D-M8…D-M11: las aprobadas en la misión (se anotan en SPEC-multifuente.md).
- **D-C1 (usuario, 2026-09-23) · Modelo de documentos.** Se mantiene la regla
  actual: el modelo de documentos guardado en Ajustes manda; sin guardado, el
  Pro 3.x más reciente de `models.list`. El usuario elegirá el modelo en
  Ajustes antes de la verificación real (E8).
- **D-C2 (usuario, 2026-09-23) · Radar desde el juez.** Radar en vivo muestra
  el Top 6 del juez, la lista completa de veredictos y el feed de evidencia
  reciente (`evidence_items`). Se retiran de la interfaz el tablero y el feed
  antiguos y la vista «Control del pipeline» (escaneo por subreddit y demo);
  el escaneo vive en Fuentes. Las tablas antiguas se conservan sin escrituras.
- **D-C3 (usuario, 2026-09-23) · Ficha de oportunidad.** Se retira con el
  Blueprint, el Arquitecto y el PDF antiguos: se queda sin entrada al irse el
  tablero, y el dossier y el plan de la Fase E la sustituyen desde el panel
  del juez.
- **D-C4 (usuario, 2026-09-23) · Búsqueda.** Se reapunta a la evidencia
  multifuente (vectores `evidence_e5` + texto de `evidence_items`), con
  atribución en cada resultado. La tabla LanceDB antigua se conserva sin uso.
- **D-C5 (usuario, 2026-09-23) · Ajustes.** Se retiran de la interfaz el
  interruptor demo/real y las credenciales de Reddit del escáner antiguo;
  lo guardado en `.env` no se toca. Reddit volverá por Fuentes con adaptador.

## Supuestos

- Sin dependencias nuevas si la biblioteca estándar, numpy o el SDK instalado
  bastan (ARI, pureza y enlace promedio se implementan con numpy).
- La auditoría original (AUD-030…AUD-071) se recupera de la transcripción de
  la sesión que la produjo; el triaje cita la evidencia de cada estado.
- Topes R7 de esta misión: Gemini 15 llamadas; un escaneo real adicional de
  fuentes públicas; Reddit y X, cero.

## Comandos

- Compuerta (R3): `bash <scratchpad>/gate.sh` (con `CLIPPY=1` si hay Rust).
- Python: `python -m unittest discover -s tests`; Rust: `cargo test` en
  `ui/src-tauri`; UI: `npx --no-install tsc --noEmit -p .` en `ui`.
- Release: `npm run tauri build` en `ui` (solo con SENTRA cerrada).
- Migraciones: `pg_dump -Fc` a `F:\backups\` → `scripts/migrate.py up --dry-run`
  → `up` → verificación de solo lectura (R12).

## Límites

- Siempre: TDD (tsc como RED/GREEN en UI), compuerta tras cada commit,
  atribución en toda evidencia mostrada o exportada, autores solo como hash.
- Preguntar antes: cualquier decisión de producto no fijada; borrar tablas.
- Nunca: scraping, silenciar un aviso sin arreglar su causa, subir el límite
  del aviso de Vite, `type: ignore` sin justificar, imprimir secretos.

## Criterios de éxito

- B: truncado detectado y corregido (presupuesto de razonamiento + división
  del lote) con doble que lo reproduce; pooling de e5 verificado y fijado;
  agrupación clustering-v2 elegida por pureza/ARI con tabla del barrido y test
  de regresión; re-juicio de 01a0d086; veredictos con versiones.
- C: una sola fuente para el Top 6; inventario de la pipeline antigua con lo
  retirado y lo que queda (y por qué); bundle bajo 500 kB por chunk.
- D: D1–D6 cerrados; `check_untyped_defs` en tests con 0 errores.
- E: dossier y plan con esquema estricto, citas verificadas, franja «no
  recomendado», viabilidad como estimación, PDF (pypdf) y Markdown para agente,
  UI con estados e i18n, verificación real.
- F: compuerta, instalación limpia, migraciones (R12), release, push y
  fast-forward.
