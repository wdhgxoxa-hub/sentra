# CLAUDE.md — SENTRA

Léelo entero antes de tocar nada. Estado verificado el 2026-09-25 (cierre de la
Fase 1) contra git, la base y la release. Si el repo contradice este archivo,
manda el repo: corrígelo aquí en un commit aparte (`tests/test_claude_md.py`
vigila lo que más cambia).

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
| Motor | `core/` — FastAPI en loopback con token. `core/sources` (adaptadores), `core/judge` (juez), `core/llm` (Gemini, control, estimación), `core/documents` (dossier y plan), `core/evidence` (búsqueda) |
| Base | PostgreSQL 18 local, base `reddit_intelligence_radar`, esquema `radar`. Rol `sentra_owner` (dueño, sin superusuario, no crea bases); los tests usan `sentra_pruebas` (solo CREATEDB, bases `rir_*_test`). DSN: `RIR_PG_URL` o, por defecto, `postgresql://sentra_owner@localhost:5432/reddit_intelligence_radar` con el pgpass de SENTRA |
| pgpass de SENTRA | `%LOCALAPPDATA%\SENTRA\pgpass.conf` (icacls: solo el usuario). El compartido `%APPDATA%\postgresql\pgpass.conf` **nunca se escribe**. Roles y pgpass: `python -m scripts.rol_sentra` (`--en-seco`, `--deshacer`); las contraseñas las teclea Walter |
| Vectores | LanceDB en `data/lancedb` (tabla `evidence_e5`) |
| Modelo e5 | `%LOCALAPPDATA%\SENTRA\models` (2,1 GB) |
| Release | `ui/src-tauri/target/release/sentra.exe`; el acceso `Desktop\SENTRA.lnk` apunta ahí |
| Motor de la release | se desempaqueta en `%LOCALAPPDATA%\com.sentra.desktop\motor\<huella>` (AUD2-003) |
| Logs de la app | `%LOCALAPPDATA%\com.sentra.desktop\logs\` (`SENTRA.log` en UTC, `sidecar.log`) |
| Migraciones | `sql/migrations/001…019`; `scripts/migrate.py up` o `status`, con `--dry-run` |
| Re-juicio sin escanear | `scripts/rejuzgar.py --run <id> --max-llamadas N --max-etiquetas N` |
| Respaldos | `F:\backups\reddit_intelligence_radar_<fecha>_<hora>_<motivo>.dump` |
| Archivo | repos clonados y scripts antiguos en `F:\archivo_sentra\` |
| psql | `C:\PostgreSQL\18\bin\psql.exe` (no está en el PATH) |

Documentos: `README.md` (puesta en marcha, compuerta, humo),
`docs/proceso.md` (reglas de proceso), `docs/auditoria-2026-09-24.md`
(auditoría AUD2 y su cierre), `docs/triaje-auditoria.md`,
`tasks/plan-fuentes-y-e8.md` (último plan de E8; su contador de Gemini es
obsoleto), `tasks/SPEC-*.md` (decisiones D-M* y D-C*).

## Fuentes (10 adaptadores en `core/sources`)

Hacker News, Stack Exchange (CC BY-SA 4.0, se muestra), GitHub, Bluesky,
YouTube (solo comentarios, no títulos), Mastodon, Discourse (foros de
facturación en `RIR_DISCOURSE_FORUMS`), Product Hunt (token verificado).

- **Reddit NO funciona**: espera la aprobación de su API. No darlo por operativo.
- **X apagada**: sin credencial, es de pago.
- Una fuente en error no entra en el escaneo hasta probarla con éxito (AUD2-012).
- Topes por fuente y escaneo (`core/sources/budget.py`): 25 peticiones y 500
  ítems por defecto; YouTube 2 000 unidades / 200 peticiones; Discourse 100
  peticiones. YouTube cobra los ítems después de quitar repetidos (Fase 1);
  el vídeo repetido se sigue releyendo (1 unidad por relectura).
- Cómo terminó cada fuente en cada ejecución (motivo de parada incluido):
  `run_source_outcomes` (migración 018).

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
- El resumen del juez queda con la ejecución (`pipeline_runs.judge_summary`,
  migración 019). `stored` = piezas guardadas por la ejecución (0 en un re-juicio).
  `filtered_in`, `filtered_out`, `analyzed`, `qualified`, `rejected`, `cycles`,
  `last_cursor` y `graph_version` son de la pipeline antigua, sin uso.

## Presupuesto de Gemini (real desde la Fase 1)

- **Punto único de control** (`core/llm/control.py`): `GeminiProvider` no se crea
  sin `ControlDeGemini`. Cada intento (reintentos y fallos incluidos) deja una
  fila en `llm_usage` (migración 017): `ok`, `error` o `cortada` (con el motivo en
  `error_code`). Propósitos: etiquetado, g0, abogado, dossier, plan,
  prueba_clave, listado_modelos, otros. Guardia AST: el SDK solo vive en
  `core/llm/gemini.py` (`tests/test_punto_unico_gemini.py`).
- **Topes** (`llm_budget_settings`, Configuración › Presupuesto de Gemini):
  por escaneo 20 llamadas y 500 000 tokens; por día 40 llamadas y 1 000 000
  tokens, día en hora de Lima. Un escaneo o un re-juicio = un control con tope
  por escaneo; dossier y plan solo tope diario. El listado de modelos se
  registra, pero ni cuenta ni se corta. Al cortar: fila `cortada`,
  `LLMBudgetExhausted(motivo)` y `pipeline_runs.stop_reason` (migración 018).
- **Confirmación obligatoria**: `POST /api/scan/estimate` da un rango estimado de
  llamadas (0 a ⌈tope de etiquetas/20⌉ + 3 + 1) y tokens (media de `llm_usage`,
  25 000 por llamada sin historial), lo gastado y lo que queda, y un
  identificador de un solo uso (10 min). `POST /api/sources/scan/stream` sin él,
  caducado, usado o de otro perfil: 409. En la interfaz, «Escanear» solo estima
  y «Confirmar y escanear» escanea.
- El historial empieza el 2026-09-25 (el contador manual anterior, 42 llamadas,
  no se puede probar y no está en la tabla).

## La compuerta (0 errores, 0 avisos, siempre)

```bash
CLIPPY=1 AUDIT=1 HUMO=1 bash scripts/compuerta.sh           # la completa: la que ejecuta el hook
bash scripts/compuerta.sh                                   # la reducida, para iterar a mano
```

Pasos: ruff, mypy, tests Python (`unittest`), tsc, node (`npm test`), cargo
test, clippy `-D warnings`, pip-audit, cargo-audit y la prueba de humo del exe
real (`python -m tests.humo_exe`). El hook `.githooks/pre-commit` ejecuta la
**completa** en cada commit (`git config core.hooksPath .githooks`); tarda unos
7 minutos. Nunca `--no-verify`.

- **Nunca `compuerta | tail && git commit`**: el `&&` mira a `tail`. La salida
  del commit va entera a un log; se lee el log después.
- La compuerta usa el `python` del sistema (3.12), no `.venv`.
- Si el commit cambia la interfaz o el motor, se recompila antes la release
  (`cd ui && npm run tauri build`): el humo prueba el exe compilado. Un `cargo
  build --release` suelto deja un exe sin interfaz en la ruta del acceso.
- Antes de compilar o del humo: comprobar con `Get-Process` que SENTRA está
  cerrada (puede estar abierta en otro workspace de GlazeWM).
- El humo usa un perfil de WebView aislado, no pulsa botones, sirve al exe una
  caché de modelos fresca (`RIR_CACHE_MODELOS`: no llama a Google) y falla si
  aparece una fila nueva en `llm_usage`.
- **Los tests no pueden tocar la base real**: `tests/__init__.py` instala una red
  (`tests/_base_real.py`) que apunta `RIR_PG_URL` a una base inexistente y
  rechaza cualquier conexión a `reddit_intelligence_radar`; solo el humo la
  libera. Las bases desechables se borran con `borrar_base_de_prueba` (sin FORCE:
  un rol sin superusuario no puede terminar un autovacuum).

## Reglas de ejecución

- Una rama por fase. A `main` solo por fast-forward, con compuerta completa en
  verde. No se fusiona ni se empuja sin que Walter lo pida.
- Commits atómicos. El mensaje dice qué test falló primero (RED) y cómo quedó (GREEN).
- **Gemini y escaneos reales: solo con aprobación de Walter en el chat**
  (cuántas llamadas y para qué). El uso queda en `llm_usage`.
- **D&S Factory comparte PostgreSQL**: antes de tocar la base o de un commit
  (sus tests crean bases), comprobar que no tiene tests, compuertas ni
  migraciones en marcha ni sesiones activas (no idle). Su app abierta en reposo
  no cuenta. Se hace uno y luego el otro.
- Nada de borrar ni cambiar datos reales, ni migraciones destructivas, sin
  respaldo `pg_dump -Fc` y aprobación. Migración que el código necesite (R12):
  respaldo + ensayo sobre copia restaurada + `--dry-run` + `migrate.py up` (como
  `sentra_owner`) + verificación en solo lectura, ANTES de abrir la app.
- Consultas a la base para verificar: siempre en solo lectura
  (`PGOPTIONS="-c default_transaction_read_only=on"`). En Git Bash no poner
  «·» ni tildes en las consultas en línea (codificación).
- Ediciones con Edit/Write o scripts escritos con Write; heredoc y `sed`
  corrompen barras invertidas y CRLF.
- «Verificado» solo con datos: antes y después sobre la app real y contrastado
  con SQL. Un DOM no vacío o un test verde no bastan.

## Estado verificado (2026-09-25, cierre de la Fase 1)

- `main` = `origin/main` = `b27c946` (Fase 0). La Fase 1 está en la rama
  `fase1/deuda`, sin fusionar ni empujar, a la espera de Walter.
- Base: 19 de 19 migraciones aplicadas. 27 ejecuciones, 67 veredictos (24
  INVESTIGAR MÁS, 43 DESCARTAR, 0 CONSTRUIR), 2 221 piezas, 1 018 etiquetas,
  6 resultados en la caché de G0. `llm_usage` vacía; topes 20 / 500 000 / 40 /
  1 000 000. Ninguna ejecución antigua tiene `stop_reason`, `judge_summary` ni
  filas en `run_source_outcomes` (no se inventa el pasado).
- Primer nicho coherente: «Tener que reclamar facturas impagadas» →
  INVESTIGAR MÁS (regla 9), re-juicio `01a0d5a3-0dc2-7ec8-afbe-a94a28314550`.
  Su dossier no se ha regenerado con el nombre nuevo (1 llamada; espera aprobación).
- Última ejecución `01a0d5d0-f8a1-736c-896d-3651c7b39afc` («Cobros freelance»,
  solo «facturas impagadas»): 470 piezas (455 únicas), casi todo YouTube, 38
  etiquetadas → 1 dolor → 0 nichos. Tema en un solo idioma = consultas solo en
  español. El Radar enseña la última ejecución juzgada aunque no tenga nichos:
  el nicho de impagos no se ve en el Radar (humo: «Top 0+0»).

## Pendiente (Walter aprueba cada fase)

1. **Fase 1:** revisión y fusión de `fase1/deuda` (decide Walter).
2. **Fase 2 — interfaz.** El escaneo está al fondo de Fuentes, el campo Tema no
   guía ni avisa de palabras clave insuficientes, «0 grupos» no dice qué hacer,
   el progreso por fuente es técnico y el Radar pierde el último nicho tras un
   escaneo vacío. Dirección a diseñar y aprobar antes de construir: «Nuevo
   escaneo» como pantalla principal con asistente de 3 pasos (tema → palabras
   clave es/en propuestas y editables → escanear), aviso de presupuesto y
   cobertura, resultado en lenguaje llano con el siguiente paso, veredictos
   visibles sin navegar, rediseño visual. Primero propuesta escrita con flujo
   y maquetas; luego construcción; luego prueba en el exe real con capturas.
3. **Fase 3 — validación por Walter:** 3–4 escaneos de temas distintos
   leyendo la evidencia de cada veredicto.
4. **Fase 4 — modo Videos**, en rama nueva. Walter tiene su propio prompt de
   arquitectura: no diseñarlo por cuenta propia.
5. **Reddit:** espera aprobación externa; sesga el radar hacia nichos de
   desarrolladores. No bloquea.
