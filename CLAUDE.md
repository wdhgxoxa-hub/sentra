# CLAUDE.md — SENTRA

Léelo entero antes de tocar nada. Estado verificado el 2026-09-24 (Fase 0,
reconocimiento en solo lectura) contra git, la base y la release. Si el repo
contradice este archivo, manda el repo: corrígelo aquí en un commit aparte.

## Qué es

SENTRA es el radar personal de nichos de Walter (uso personal).
Lema: «Escucha el mercado antes de construir».

Flujo: escanear fuentes → filtrar → etiquetar con LLM (Gemini, vía
`LLMProvider`) → agrupar con e5 por la frase del problema verificada
(`is_pain`, umbral 0,82) → juez con compuertas G0–G8 → veredicto
CONSTRUIR / INVESTIGAR MÁS / DESCARTAR → dossier y plan (PDF y Markdown).

## Roles y forma de trabajar

- Walter es el arquitecto y decide. El agente ejecuta, verifica y reporta.
- Español, frases cortas. Arreglos de causa raíz, nunca parches.
- Nada de progreso inventado. Nada de «debería funcionar».
- Nada está terminado sin probarlo en la release real, no solo en tests.
- Reporte = qué se hizo + evidencia (comando y resultado, o captura) + qué falta.
- Walter aprueba cada fase antes de empezarla. Si algo no está especificado
  y es de negocio o diseño: se proponen opciones medidas y él elige.

## Dónde está cada cosa

| Pieza | Dónde |
|---|---|
| Repo | `F:\reddit_intelligence_radar` · GitHub `wdhgxoxa-hub/sentra` (público) |
| Interfaz | `ui/src` — React 19 + TypeScript. Vistas: Radar, Búsqueda, Fuentes, Configuración |
| Escritorio | `ui/src-tauri` — Tauri 2 (Rust): IPC, arranque del motor, salud |
| Motor | `core/` — FastAPI en loopback con token. `core/sources` (adaptadores), `core/judge` (juez), `core/llm` (Gemini), `core/documents` (dossier y plan), `core/evidence` (búsqueda) |
| Base | PostgreSQL 18 local, base `reddit_intelligence_radar`, esquema `radar`. DSN: `RIR_PG_URL` (por defecto `postgresql://postgres@localhost:5432/reddit_intelligence_radar`) |
| Vectores | LanceDB en `data/lancedb` (tabla `evidence_e5`) |
| Modelo e5 | `%LOCALAPPDATA%\SENTRA\models` (2,1 GB) |
| Release | `ui/src-tauri/target/release/sentra.exe`; el acceso `Desktop\SENTRA.lnk` apunta ahí |
| Motor de la release | se desempaqueta en `%LOCALAPPDATA%\com.sentra.desktop\motor\<huella>` (AUD2-003) |
| Logs de la app | `%LOCALAPPDATA%\com.sentra.desktop\logs\` (`SENTRA.log`, `sidecar.log`) |
| Migraciones | `sql/migrations/001…016`; `scripts/migrate.py up` o `status`, con `--dry-run` |
| Re-juicio sin escanear | `scripts/rejuzgar.py --run <id> --max-llamadas N --max-etiquetas N` |
| Archivo | repos clonados y scripts antiguos en `F:\archivo_sentra\` |
| psql | `C:\PostgreSQL\18\bin\psql.exe` (no está en el PATH) |

Documentos: `README.md` (puesta en marcha, compuerta, humo),
`docs/proceso.md` (reglas de proceso), `docs/auditoria-2026-09-24.md`
(auditoría AUD2 y su cierre), `docs/triaje-auditoria.md`,
`tasks/plan-fuentes-y-e8.md` (último plan, con cifras y llamadas de Gemini),
`tasks/SPEC-*.md` (decisiones D-M* y D-C*).

## Fuentes (10 adaptadores en `core/sources`)

Hacker News, Stack Exchange (CC BY-SA 4.0, se muestra), GitHub, Bluesky,
YouTube (solo comentarios, no títulos), Mastodon, Discourse (foros de
facturación en `RIR_DISCOURSE_FORUMS`), Product Hunt (token verificado).

- **Reddit NO funciona**: espera la aprobación de su API. No darlo por operativo.
- **X apagada**: sin credencial, es de pago.
- Una fuente en error no entra en el escaneo hasta probarla con éxito (AUD2-012).
- Topes por fuente y escaneo (`core/sources/budget.py`): 25 peticiones y 500
  ítems por defecto; YouTube 2 000 unidades / 200 peticiones; Discourse 100 peticiones.

## Reglas del juez ya decididas (no se cambian sin aprobación)

- **G0 coherencia por LLM.** Grupo mezclado = «sin problema común», sin
  puntuación, nunca CONSTRUIR. Si hay un problema dominante, se separa en
  subgrupo confirmado. Caché de G0 por grupo (`coherence_checks`).
  Temperatura por defecto (no 0: Google lo desaconseja en Gemini 3).
- **Anuncios de herramientas** («construí X», «Show HN») = competencia, nunca dolor.
- **Regla de 3 autores (G7).** Un competidor gratuito solo cuenta si lo
  nombran ≥ 3 autores distintos. Con 1–2: G7 «sin datos suficientes» y el
  veredicto no pasa de INVESTIGAR MÁS (regla 9).
- **Dossier.** Una afirmación general exige ≥ 2 autores; si no, se marca
  «Anécdota (1 autor)».
- **Nombre del grupo.** Lo produce G0 en es/en y se guarda con el veredicto
  (`niche_verdicts.problem_name`, migración 016).
- Versiones vigentes: labels-v4, clustering-v10, coherence-v3, judge-weights-v6.

## La compuerta (0 errores, 0 avisos, siempre)

```bash
CLIPPY=1 AUDIT=1 HUMO=1 bash scripts/compuerta.sh           # ANTES DE CADA COMMIT, con SENTRA cerrada
bash scripts/compuerta.sh                                   # la que ejecuta el hook de pre-commit
```

Regla de Walter (2026-09-24): la compuerta **completa** (`CLIPPY=1 AUDIT=1
HUMO=1`) en verde antes de cada commit, no solo antes de cada release. El
hook ejecuta la reducida; la completa se lanza a mano y el commit solo sale
si su código de salida es 0.

Pasos: ruff, mypy, tests Python (`unittest`), tsc, node (`npm test`),
cargo test; con banderas: clippy `-D warnings`, pip-audit, cargo-audit y la
prueba de humo del exe real (`python -m tests.humo_exe`).

- El hook `.githooks/pre-commit` la exige (`git config core.hooksPath .githooks`). Nunca `--no-verify`.
- **Nunca `compuerta | tail && git commit`**: el `&&` mira a `tail`. Redirigir a
  un log, guardar `rc=$?` y decidir con `rc`.
- La compuerta usa el `python` del sistema (3.12), no `.venv`.
- La release se compila **solo** con `cd ui && npm run tauri build`. Un
  `cargo build --release` suelto deja un exe sin interfaz en la ruta del acceso.
- Antes de compilar o del humo: comprobar con `Get-Process` que SENTRA está
  cerrada (puede estar abierta en otro workspace de GlazeWM).
- El humo usa un perfil de WebView aislado y no pulsa botones. Al abrir
  Configuración puede listar modelos en Google si la lista guardada tiene más
  de un día (sin tokens, pero es una salida a la red).

## Reglas de ejecución

- Una rama por fase. A `main` solo por fast-forward, con compuerta de release
  en verde y humo OK. No se empuja sin que Walter lo pida.
- Commits atómicos. El mensaje dice qué test falló primero (RED) y cómo quedó (GREEN).
- **Gemini: cada llamada se avisa antes** (cuántas y para qué) y se anota
  después con su motivo y sus tokens. Un escaneo etiqueta ⌈piezas que pasan
  el filtro / 20⌉ llamadas (máx. 300 piezas → 15) + G0 + confirmaciones de
  subgrupos; el dossier gasta 1.
- Nada de borrar datos ni migraciones destructivas sin respaldo `pg_dump -Fc`
  y aprobación. Migración que el código necesite: respaldo + `migrate.py up`
  + verificación en solo lectura ANTES de abrir la app.
- Consultas a la base para verificar: siempre en solo lectura
  (`PGOPTIONS="-c default_transaction_read_only=on"`). En Git Bash no poner
  «·» en las consultas (codificación).
- Ediciones con Edit/Write; heredoc y `sed` corrompen barras invertidas y CRLF.
- «Verificado» solo con datos: antes y después sobre la app real y contrastado
  con SQL. Un DOM no vacío o un test verde no bastan.

## Estado verificado (2026-09-24, Fase 0)

- `main` = `origin/main` = `c9c3fb5`. La rama `feat/cierre-y-documentos` es el
  mismo commit. Árbol limpio.
- Base: 16 de 16 migraciones aplicadas. 27 ejecuciones (5 multifuente, 14
  re-juicios, 8 del esquema antiguo). 67 veredictos (24 INVESTIGAR MÁS, 43
  DESCARTAR, 0 CONSTRUIR). 2 221 piezas de evidencia. 6 resultados en la caché de G0.
- Release compilada a las 17:59, después del último cambio de producto (6f16968).
- Primer nicho coherente: «Tener que reclamar facturas impagadas» →
  INVESTIGAR MÁS (regla 9), re-juicio `01a0d5a3-0dc2-7ec8-afbe-a94a28314550`.
- Última ejecución `01a0d5d0-f8a1-736c-896d-3651c7b39afc` (perfil «Cobros
  freelance», tema solo «facturas impagadas», idiomas es/en): 470 piezas
  traídas: YouTube 419, Bluesky 44, Mastodon 6, GitHub 1; HN, Stack Exchange,
  Discourse y Product Hunt 0. 434 sin idioma, 33 es, 1 en. Todas las consultas
  salieron en español (`sidecar.log`).
  38 etiquetadas → 1 dolor → 0 grupos, 0 veredictos. `pipeline_runs.filtered_in`
  quedó en 0 aunque 38 se etiquetaron. Esa ejecución gastó 2 llamadas de
  Gemini (`gemini-3.8-flash`, en `sidecar.log`).
  - **Únicos: 455.** Es lo que enseña la app («{canonical} únicos»,
    `ui/src/i18n/es.ts:286`): 470 − 15 duplicados de `evidence_duplicates`
    (7 por huella de texto, 8 por embedding ≥ 0,95, `core/sources/dedup.py:34`).
    Contando solo `content_hash` distintos salen 463: es otro criterio.
  - **YouTube se paró por su tope de 500 ítems**, no por unidades (usó 318
    de 2 000 y 21 de 200 peticiones). 13 vídeos distintos = 419 comentarios
    guardados; 2 vídeos se releyeron (50 + 31 ítems) y 419 + 50 + 31 = 500.
    Causas: `SourceAdapter._item` (`core/sources/base.py:283`) cobra el ítem
    antes de que YouTube descarte el repetido (`core/sources/youtube.py:128`),
    así que los duplicados gastan presupuesto (81 de 500). El motivo de
    parada solo viaja en el evento `scan:done` a la interfaz
    (`core/orchestration/sidecar/multiscan.py:249`); no se guarda en la base.
  - **El Radar enseña la última ejecución juzgada aunque no tenga nichos**
    (`core/judge/store.py:123`): desde este escaneo el nicho de impagos no se
    ve en el Radar (humo: «Top 0+0»).

## Presupuesto de Gemini: cómo funciona de verdad

- En el código solo hay un tope de **tokens por escaneo**: `LLMBudget`,
  1 000 000 (`core/llm/budget.py`, constante, no configurable) y un tope de
  piezas etiquetadas (`MAX_ITEMS_PER_SCAN` = 300, o `RIR_JUEZ_MAX_ETIQUETAS`).
- El «presupuesto de 40 llamadas» es un **contador de proceso** acordado con
  Walter y anotado en `tasks/plan-fuentes-y-e8.md`. La app no lo conoce, no
  lo muestra y no lo hace cumplir. Cuenta real: 40 de ese plan + 2 del
  escaneo «Cobros freelance» = 42.
- El aviso `llm_budget_exhausted` de la interfaz dice «Súbelo en Ajustes»,
  pero Ajustes no tiene ese control: el texto miente.

## Pendiente (orden propuesto; Walter aprueba cada fase)

1. **Fase 1 — deuda pequeña.**
   - Presupuesto de Gemini visible y real en la app antes de escanear
     (llamadas estimadas del escaneo y lo gastado), y corregir «Súbelo en Ajustes».
   - `.gitattributes` para `ui/src-tauri/Cargo.toml` (hoy índice LF, trabajo
     CRLF con `core.autocrlf=true`; en reposo no sale modificado: reproducir
     tras `tauri build` antes de arreglar).
   - Revisar si `pipeline_runs.filtered_in` = 0 en las ejecuciones
     multifuente es un fallo o una columna que ese flujo no usa.
   - Regenerar el dossier de impagos con el nombre nuevo (1 llamada, con aprobación).
2. **Fase 2 — interfaz.** Hoy el escaneo está al fondo de Fuentes, el campo
   Tema no guía, no avisa de palabras clave insuficientes, «0 grupos» no dice
   qué hacer y el progreso por fuente es técnico. Dirección a diseñar y
   aprobar antes de construir: «Nuevo escaneo» como pantalla principal con
   asistente de 3 pasos (tema → palabras clave es/en propuestas y editables →
   escanear), aviso de presupuesto y cobertura, resultado en lenguaje llano con
   el siguiente paso, veredictos visibles sin navegar, rediseño visual.
   Primero propuesta escrita con flujo y maquetas; luego construcción; luego
   prueba en el exe real con capturas.
3. **Fase 3 — validación por Walter:** 3–4 escaneos de temas distintos
   leyendo la evidencia de cada veredicto.
4. **Fase 4 — modo Videos**, en rama nueva. Walter tiene su propio prompt de
   arquitectura: no diseñarlo por cuenta propia.
5. **Reddit:** espera aprobación externa; sesga el radar hacia nichos de
   desarrolladores. No bloquea.
