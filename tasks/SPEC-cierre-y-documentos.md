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
- **D-C6 (usuario, 2026-09-23) · Renombrado completo (AUD-066).** Todo a
  SENTRA, identificador de Tauri incluido: la app estrena carpeta de datos y
  de logs (idioma y tema vuelven a los valores por defecto) y SENTRA.lnk se
  revisa en la fase F. Las claves `RIR_*` del `.env` y el nombre de la base de
  datos no son restos visibles y no cambian (cambiarlos obligaría a migrar
  secretos y datos).
- **D-C7 (usuario, 2026-09-23) · Demos antiguas (AUD-038, AUD-043).** Se
  retiran `demo_ingestion.py`, `demo_intelligence.py` y lo que solo ellos
  usaban (cliente, filtro, normalizador y paginador de ingestion; NLI, JTBD,
  puntuación temporal y clustering de intelligence). Se conserva lo que usa el
  adaptador de Reddit (auth, errores, User-Agent).
- **D-C8 (usuario, 2026-09-23) · Sin CI (AUD-052).** La compuerta local es la
  CI del proyecto y el README explica cómo pasarla; eslint/prettier no se
  añaden (serían dependencias nuevas): en la UI hace de lint `tsc` estricto.

## Fase E — diseño

Del veredicto a dos documentos: el **dossier** (cualquier veredicto: para
decidir) y el **plan de construcción** (para ejecutarlo paso a paso). El
contenido de mercado lo redacta el modelo de documentos (D-C1) con
`generate_json`; el formato, los avisos, la franja y la marca de agua los
escribe el código, nunca el modelo.

**Afirmaciones con cita.** Toda afirmación de mercado (problema, quién lo
sufre, cómo se resuelve hoy, oportunidad, riesgos, alcance del MVP,
criterios de validación, plan de publicación) es un `Claim {text,
evidence_ids}`. La cita tiene que ser un id de la evidencia de ese veredicto;
una afirmación sin ids o con un id que no es del veredicto se retira entera y
el documento lo dice con un aviso («N afirmaciones retiradas por citar
evidencia inexistente»). Si una sección se queda vacía, el código escribe
«Sin afirmaciones verificables», nunca relleno. Lo técnico del plan (stack,
arquitectura, modelo de datos, pasos) no es una afirmación de mercado y no
lleva cita.

**Dossier** (secciones fijas, en este orden): 1 Resumen del veredicto
(código: veredicto, puntuación, regla, compuertas que faltan); 2 El problema;
3 Quién lo sufre; 4 Cómo lo resuelven hoy; 5 Por qué ahora (oportunidad);
6 Compuertas y dimensiones (código); 7 Abogado del diablo (código); 8
Viabilidad — estimación del modelo (E3); 9 Riesgos; 10 Evidencia citada
(código: extracto, fecha y atribución de cada pieza citada); 11 Procedencia
(código: ejecución, versiones, modelo, fecha, fuente de los datos).

**Plan** (solo para CONSTRUIR; forzable en otro veredicto, y entonces cada
página lleva la franja «El juez no recomienda construir este nicho: <regla>»):
1 Qué se construye y para quién; 2 Alcance del MVP (dentro / fuera, con
cita); 3 Stack; 4 Arquitectura; 5 Modelo de datos; 6 Diez pasos, cada uno con
objetivo, archivos, comandos, pruebas de aceptación y criterio de hecho
(exactamente 10); 7 Validación tras el lanzamiento (con cita); 8 Plan de
publicación (con cita: dónde está la gente que se quejó); 9 Procedencia.

**Viabilidad (E3).** Rúbrica fija de cinco criterios (complejidad técnica,
tiempo hasta un MVP, dependencias externas, coste de conseguir usuarios,
riesgo legal) con nota 1–5 y motivo, etiquetada «Estimación del modelo: no es
un dato medido y no cambia el veredicto». No toca compuertas ni puntuación.

**Llamadas.** Una por documento, con presupuesto de razonamiento y límite de
salida. Si se trunca (`LLMTruncated`), el esquema se parte en dos mitades y se
pide cada una (una sola división: tope de 3 llamadas por documento). El
sidecar guarda en memoria lo generado por (veredicto, documento, idioma,
modelo, forzado): exportar PDF y luego Markdown no vuelve a llamar.

**Salidas.** PDF (ReportLab, la fuente incrustada de `core/documents`, con
tildes y ñ) y Markdown para un agente, ambos desde el mismo modelo de
documento, guardados con el diálogo nativo. Marca de agua «DATOS DE
DEMOSTRACIÓN» solo si alguna pieza del veredicto es de demostración. El
idioma es el de la interfaz. `blueprint.py` y el documento por cluster
antiguo se retiran (AUD-049; AUD-050 se cierra con la procedencia y las
citas).

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
