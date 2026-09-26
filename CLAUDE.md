# CLAUDE.md — SENTRA

Léelo entero antes de tocar nada. Estado verificado el 2026-09-25 (construcción
de la Fase 2, rama `fase2/interfaz`) contra git, la base y la release. Si el repo contradice este archivo,
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
| Interfaz | `ui/src` — React 19 + TypeScript. Pantallas: **Nuevo escaneo** (la principal, asistente de 3 pasos), Radar (con la ficha de cada nicho), Búsqueda, Fuentes, Configuración. `pantallas/` y `components/nicho/` son genéricas (P2); `views/` son las páginas del modo Software y las compartidas |
| Escritorio | `ui/src-tauri` — Tauri 2 (Rust): IPC, arranque del motor, salud |
| Motor | `core/` — FastAPI en loopback con token. `core/sources` (adaptadores), `core/judge` (juez), `core/llm` (Gemini, control, estimación), `core/documents` (dossier y plan), `core/evidence` (búsqueda) |
| Base | PostgreSQL 18 local, base `reddit_intelligence_radar`, esquema `radar`. Rol `sentra_owner` (dueño, sin superusuario, no crea bases); los tests usan `sentra_pruebas` (solo CREATEDB, bases `rir_*_test`). DSN: `RIR_PG_URL` o, por defecto, `postgresql://sentra_owner@localhost:5432/reddit_intelligence_radar` con el pgpass de SENTRA |
| pgpass de SENTRA | `%LOCALAPPDATA%\SENTRA\pgpass.conf` (icacls: solo el usuario). El compartido `%APPDATA%\postgresql\pgpass.conf` **nunca se escribe**. Roles y pgpass: `python -m scripts.rol_sentra` (`--en-seco`, `--deshacer`); las contraseñas las teclea Walter |
| Vectores | LanceDB en `data/lancedb` (tabla `evidence_e5`) |
| Modelo e5 | `%LOCALAPPDATA%\SENTRA\models` (2,1 GB) |
| Release | `ui/src-tauri/target/release/sentra.exe`; el acceso `Desktop\SENTRA.lnk` apunta ahí |
| Motor de la release | se desempaqueta en `%LOCALAPPDATA%\com.sentra.desktop\motor\<huella>` (AUD2-003) |
| Logs de la app | `%LOCALAPPDATA%\com.sentra.desktop\logs\` (`SENTRA.log` en UTC, `sidecar.log`) |
| Migraciones | `sql/migrations/001…020`; `scripts/migrate.py up` o `status`, con `--dry-run` |
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
- Reparto (Fase 3, `fase3/reparto`): las fuentes de un escaneo comparten un
  cupo de 500 piezas (`CupoDelEscaneo`, `CUPO_POR_ESCANEO`) y ninguna pasa de
  250; lo que no usan las vacías queda para las demás. YouTube agrupa las
  palabras de 4 en 4 con «|», hace TODAS las búsquedas antes de leer
  comentarios, 25 vídeos × 10 comentarios por turnos, y no trae comentarios
  que no nombran el tema (`menciona_el_tema`): con las 14 palabras del
  escaneo 1, 430 unidades (antes 1 065). No verificado en la API real: el O
  con términos de varias palabras entre comillas. El resultado avisa si una
  fuente aporta más de la mitad (`RunOverview.sources`).
- Palabras clave: términos de 1 a 3 palabras; el idioma de cada una viaja del
  asistente (`keyword_languages`). Ventana por defecto: 1 año.
- Cómo terminó cada fuente en cada ejecución (motivo de parada incluido):
  `run_source_outcomes` (migración 018).
- **D-M12 · Dirección del original con el DID (Walter, 2026-09-25).** Sigue a
  D-M1…D-M11 de `tasks/SPEC-multifuente.md`. R5 gana solo para el enlace: la
  dirección se guarda completa (la de Bluesky lleva el DID; sin ella no se
  verifica la evidencia), pero el DID nunca se ve como texto en ninguna
  pantalla ni documento (R9).
  - Pantalla: se ve `direccionVisible` (`bsky.app/profile/…/post/<id>`) y
    «Copiar dirección» lleva la completa en `data-destino`.
  - Documentos: Markdown `[visible](completa)` y PDF `<a href>`. Todo texto
    pintado oculta DID y at:// (`core/privacidad.py`), también lo guardado antes
    de los alias, que no se reescribe (decisión de Walter).
  - Guardia: el humo busca identificadores en el texto visible de cada pantalla
    («Ver detalle» abiertos, texto ajeno incluido) sin excepción para las
    direcciones; el destino de un botón no es texto.

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

## Interfaz (Fase 2): principios que se vigilan

- **P1, facilidad de uso.** Nada de jerga en lo que se ve: la lista única de
  palabras prohibidas está en `tests/_lenguaje_llano.py` (tokens, G0–G9,
  cluster, pipeline, regla N, LLM, API, JSON, compuerta, run…). Tres guardias:
  i18n (`tests/test_lenguaje_llano.py`: todo salvo el bloque `detalle`), `t.detalle`
  solo en `components/detalle/` (se pinta dentro de «Ver detalle»), y el humo, que
  lee el texto visible del exe en cada pantalla. Las citas de la evidencia, los
  nombres de nichos y las URL van con `data-ajeno` (son datos, no se tocan).
  Una sola `AccionPrincipal` por pantalla del asistente, del Radar y de la ficha
  (el humo las cuenta). Letra de al menos 12 px salvo el detalle técnico. Cada
  estado lleva palabra e icono, no solo color. Tokens «unidades de texto».
  Ningún `<a href>` externo: la ventana no abre enlaces.
- **Radar.** Enseña la última ejecución **con nichos** (`latest_run_with_niches`,
  algún veredicto que no sea DESCARTAR); si la última juzgada es otra, un aviso con
  su nombre y fecha y su resultado al pulsar. `latest_judged_run` no cambia.
  `GET /api/judge/top` añade `run` y `latestRun` (`RunOverview`).
- **Documentos.** `GET /api/documents/status?verdictId=` dice si dossier y plan
  están guardados (solo mira el disco). Exportar algo guardado lo reutiliza sin
  resolver el modelo (0 llamadas); cambiar de modelo no regenera lo guardado.
- **Palabras clave.** `POST /api/scan/keywords`: con Gemini, 1 llamada
  `palabras_clave` (migración 020) dentro de los topes; sin clave, sin
  presupuesto o con error, plantillas sin Gemini y `reason` dice por qué.

## Modo Videos: cómo se enchufa (P2; no está construido)

Walter tiene su propio prompt de arquitectura para el modo Videos: no se
diseña por cuenta propia. Lo que la Fase 2 deja listo:

1. `ui/src/modos/tipos.ts` define `Modo` (textos del asistente y cómo se dice
   una métrica) y `NichoEnPantalla` (el tipo de nicho es un dato).
2. Se escribe `ui/src/modos/videos.ts` con sus textos, sus métricas y su
   adaptador `nichoDeVideos`, y se registra en `ui/src/modos/registro.ts`. Con dos
   modos, el `SelectorDeModo` de la barra lateral aparece solo.
3. `ui/src/lib/nichos.ts` lee los nichos del modo activo: se le añade la
   lectura de Videos (su ruta del motor la define Walter).
4. `pantallas/` (asistente, resultado, Radar, ficha) y `components/nicho/` no
   se tocan: `tests/test_modo_videos_preparado.py` impide que dependan del modo
   Software. Fuentes y Configuración son compartidas.
5. No verificado aún: los componentes genéricos pintados con un nicho de tipo
   «videos» (no hay pruebas de componentes con DOM sin dependencias nuevas).

## Presupuesto de Gemini (real desde la Fase 1)

- **Punto único de control** (`core/llm/control.py`): `GeminiProvider` no se crea
  sin `ControlDeGemini`. Cada intento (reintentos y fallos incluidos) deja una
  fila en `llm_usage` (migración 017): `ok`, `error` o `cortada` (con el motivo en
  `error_code`). Propósitos: etiquetado, g0, abogado, dossier, plan,
  prueba_clave, listado_modelos, otros y palabras_clave (migración 020: el asistente
  de escaneo propone palabras clave, Fase 2). Guardia AST: el SDK solo vive en
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

## Estado verificado (2026-09-25, construcción de la Fase 2)

- `main` = `origin/main` = `2688c3d` (Fases 0 y 1). La Fase 2 está en la rama
  `fase2/interfaz`, sin fusionar ni empujar, a la espera de Walter
  (`docs/fase2/PROPUESTA.md`, sección 7, y `docs/fase2/capturas-exe/`).
- Base: 20 de 20 migraciones (la 020 con respaldo `pre020.dump` y ensayo). 27
  ejecuciones, 67 veredictos (24 INVESTIGAR MÁS, 43 DESCARTAR, 0 CONSTRUIR),
  2 221 piezas. `llm_usage`: 2 filas (los dos dossiers de impagos, 25-09).
- El Radar enseña la ejecución del 24-09 17:56 (1 nicho: «Tener que reclamar
  facturas impagadas», INVESTIGAR MÁS por la regla 9, 9 personas; 3 descartados)
  y avisa de que la del 24-09 18:47 («Cobros freelance») no formó nichos. Su
  dossier está guardado en `%LOCALAPPDATA%\SENTRA\documentos` (se abre sin gastar).
- Mastodon: desde e6c5b95 el adaptador guarda la dirección pública del mensaje
  (`https://<instancia>/statuses/<id>`, sin @usuario). Las 223 piezas anteriores
  se corrigieron el 25-09 con aprobación de Walter (respaldo
  `pre_mastodon_url.dump`; 0 URL con `/api/v1/`; resto de datos con huella
  idéntica), igual que el dossier guardado y su copia (con `.bak`).
- Fase 3 lista: `docs/fase3/GUIA.md`, `REGISTRO.md` y `TEMAS.md` (los 4 temas
  elegidos por Walter, en su orden). Los escaneos los lanza Walter.
- `llm_usage`: 3 filas (dos dossiers y un `listado_modelos` del 25-09, 12:29).

## Pendiente (Walter aprueba cada fase)

1. **Fase 2 — interfaz:** construida en `fase2/interfaz`; revisión y fusión
   (decide Walter). Lo que decía la propuesta original: El escaneo está al fondo de Fuentes, el campo Tema no
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
