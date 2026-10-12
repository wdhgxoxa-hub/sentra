# CLAUDE.md — SENTRA

Radar personal de nichos de Walter (David). Lema: «Escucha el mercado antes de construir».
Las reglas generales de David están en `~/.claude/CLAUDE.md`; aquí solo lo propio de SENTRA. Si el repo contradice
este archivo, manda el repo: corrígelo aquí en un commit aparte (`tests/test_claude_md.py` vigila lo que más cambia).

Flujo: escanear fuentes → filtrar → etiquetar con LLM (Gemini, vía `LLMProvider`) → agrupar con e5 por la frase del
problema verificada (`is_pain`, umbral 0,82) → juez con compuertas G0–G8 → veredicto CONSTRUIR / INVESTIGAR MÁS /
DESCARTAR → dossier y plan (PDF y Markdown).

## Forma de trabajar
- Walter decide y aprueba cada fase antes de empezarla; lo no especificado de negocio o diseño se le propone con
  opciones medidas. Reporte = qué se hizo + evidencia (orden y resultado, o captura) + qué falta.
- Nada está terminado sin probarlo en la release real; «verificado» = antes y después sobre la app real,
  contrastado con SQL de solo lectura (`PGOPTIONS="-c default_transaction_read_only=on"`).
- Una rama por fase; a `main` solo por fast-forward con la compuerta completa en verde. La migración a Linux
  (antes rama `fase-linux/migracion`, ya no existe) está en `main`, que es la rama activa (DECISIONES 2026-10-11).
- El mensaje de cada commit dice qué test falló primero (RED) y cómo quedó (GREEN).
- **Gemini y escaneos reales: solo con aprobación de Walter en el chat** (cuántas llamadas y para qué).
- Ediciones con Edit/Write o scripts escritos con Write: heredoc y `sed` corrompen barras invertidas.

## Dónde está cada cosa
| Pieza | Dónde |
|---|---|
| Repo | `~/SENTRA/reddit_intelligence_radar` · GitHub `wdhgxoxa-hub/sentra` (público) |
| Interfaz | `ui/src` (React 19 + TS). Pantallas: **Nuevo escaneo** (principal, asistente de 3 pasos), Radar, Búsqueda, Fuentes, Configuración. `pantallas/` y `components/nicho/` son genéricas; `views/` son del modo Software y compartidas |
| Escritorio | `ui/src-tauri` (Tauri 2, Rust): IPC, arranque del motor, salud. Release: `ui/src-tauri/target/release/sentra` (`cd ui && npm run tauri build -- --no-bundle`); acceso del menú instalado con `scripts/acceso_linux.py` |
| Motor | `core/` (FastAPI en loopback con token): `sources` (adaptadores), `judge`, `llm`, `documents`, `evidence` |
| Base | PostgreSQL 18 nativo, puerto 5432 (compartido con D&S Factory), base `reddit_intelligence_radar`, esquema `radar`. Roles: `sentra_owner` (dueño) y, en tests, `sentra_pruebas` (bases `rir_*_test`). DSN: `RIR_PG_URL` o el de por omisión con el pgpass de SENTRA; puerto con `RIR_PG_PORT`. Contenedor `sentra-pg` (127.0.0.1:5438, `deploy/contenedores/`) listo; el corte espera a David |
| pgpass | `~/.local/share/SENTRA/pgpass.conf` (600). El de D&S Factory nunca se escribe. Roles: `python -m scripts.rol_sentra --admin-sudo` (`--en-seco`; usa sudo: lo corre David) |
| Datos locales | `~/.local/share/SENTRA` (`core/rutas.py::carpeta_local()` y `db.rs`; nunca `~/.cache`); modelo e5 en `models/`; vectores LanceDB en `data/lancedb` |
| Python | `.venv/bin/python` (3.12.14, de `uv`); el del sistema no se usa |
| Logs de la app | `~/.local/share/com.sentra.desktop/logs/` (`SENTRA.log` en UTC, `sidecar.log`); motor en `…/motor/<huella>` |
| Migraciones | `sql/migrations/001…021`; `scripts/migrate.py up` o `status`, con `--dry-run` |
| Re-juicio | `scripts/rejuzgar.py --run <id> --max-llamadas N --max-etiquetas N` |
| MCP (Claude Desktop) | `core/mcp/servidor.py`, registrado como `sentra`; lee y solo PROPONE escaneos (`scan_requests`). Guía `docs/mcp.md` |
| Respaldos | `~/SENTRA/backups/reddit_intelligence_radar_<fecha>_<hora>_<motivo>.dump` |

Documentos: `README.md` (puesta en marcha, compuerta, humo), `docs/DECISIONES.md` (infraestructura), `docs/proceso.md`
(reglas de proceso), `tasks/SPEC-*.md` (decisiones D-M* y D-C*), `docs/fase3/` (GUIA, REGISTRO, TEMAS),
`docs/auditoria-2026-09-24.md`, `docs/triaje-auditoria.md`.

## Pruebas y compuerta (0 errores, 0 avisos)
| Cuándo | Orden (desde el repo) |
|---|---|
| Rápida | `PYTHONIOENCODING=utf-8 .venv/bin/python -W error -m unittest tests.test_claude_md tests.test_lenguaje_llano` (13 pruebas, 0,35–0,39 s, medido el 12-10) y `PASOS="ruff mypy" bash scripts/compuerta.sh` (0,5 s) |
| A mano, al iterar | `bash scripts/compuerta.sh` (ruff, mypy, unittest con `-W error`, tsc, node, cargo) |
| Cada commit (hook `.githooks/pre-commit`) | `CLIPPY=1 AUDIT=1 HUMO=1 bash scripts/compuerta.sh` (+ clippy, pip-audit, cargo-audit y humo del exe real; unos 7 min) |

- El humo abre la release en un Xvfb propio (`:90` o más, nunca `:0`) con perfil aislado; falla si aparece una fila
  nueva en `llm_usage` o una ventana en el escritorio real. Si el commit cambia interfaz o motor, recompila antes
  con `npm run tauri build` (un `cargo build --release` suelto deja un exe sin interfaz). SENTRA cerrada antes
  (`pgrep -x sentra`).
- Los tests no tocan la base real: `tests/_base_real.py` la bloquea; solo el humo la libera.
- **D&S Factory comparte PostgreSQL**: antes de tocar la base o de un commit (sus tests crean bases), comprobar en
  solo lectura que no tiene `pytest` en marcha, 0 sesiones no idle en `pg_stat_activity` y 0 bloqueos `advisory`.
- Nada de borrar ni cambiar datos reales sin respaldo `pg_dump -Fc` y aprobación. Migración que el código necesite:
  respaldo + ensayo sobre copia + `--dry-run` + `migrate.py up` (como `sentra_owner`) + verificación, ANTES de abrir la app.

## Fuentes (`core/sources`)
Hacker News, Stack Exchange, GitHub, Bluesky, YouTube (solo comentarios), Mastodon, Discourse, Product Hunt.
**Reddit NO funciona** (espera la aprobación de su API) y **X está apagada** (de pago). Una fuente en error no entra
hasta probarla con éxito. Topes en `core/sources/budget.py`; cupo de 500 piezas útiles por escaneo y 250 por fuente
(`CupoDelEscaneo`); GitHub y Stack Exchange solo si encajan con el tipo de tema (`core/sources/encaje.py`).
Cómo terminó cada fuente: `run_source_outcomes`. DID de Bluesky: se guarda la dirección completa pero nunca se ve
como texto (`core/privacidad.py`, D-M12).

## Reglas del juez ya decididas (no se cambian sin aprobación)
- **G0** coherencia por LLM: grupo mezclado = «sin problema común», nunca CONSTRUIR; caché por grupo.
- Anuncios de herramientas («construí X», «Show HN») = competencia, nunca dolor.
- **G7, regla de 3 autores**: con 1–2, «sin datos suficientes» y como mucho INVESTIGAR MÁS. Dossier: afirmación
  general con ≥ 2 autores o «Anécdota (1 autor)».
- Solo cuentan las quejas del tema (labels-v5: `is_pain = yes` y `del_tema = yes`). Umbral de agrupación 0,82.
- Versiones: labels-v5, clustering-v10, coherence-v3, judge-weights-v6. Resumen del juez en `pipeline_runs.judge_summary`.

## Interfaz: principios que se vigilan
- Nada de jerga en lo que se ve: lista única en `tests/_lenguaje_llano.py`; `t.detalle` solo dentro de «Ver detalle»;
  citas, nombres de nichos y URL con `data-ajeno`. Una sola `AccionPrincipal` por pantalla; letra ≥ 12 px; cada estado
  con palabra e icono; ningún `<a href>` externo.
- El Radar enseña la última ejecución con nichos (`latest_run_with_niches`). `GET /api/documents/status` mira si dossier
  y plan están guardados (reutilizar = 0 llamadas). `POST /api/scan/keywords`: 1 llamada `palabras_clave` o plantillas.

## Modo Videos: cómo se enchufa (no está construido)
Walter tiene su propio prompt de arquitectura: no se diseña por cuenta propia. Preparado: `ui/src/modos/tipos.ts`;
se añade `ui/src/modos/videos.ts` y se registra en `ui/src/modos/registro.ts` (con dos modos aparece el
`SelectorDeModo`); `ui/src/lib/nichos.ts` leerá sus nichos. `tests/test_modo_videos_preparado.py` impide que lo
genérico dependa del modo Software.

## Presupuesto de Gemini
- Punto único `core/llm/control.py`: sin `ControlDeGemini` no hay `GeminiProvider`; cada intento deja fila en
  `llm_usage`. El SDK solo vive en `core/llm/gemini.py` (`tests/test_punto_unico_gemini.py`).
- Topes en `llm_budget_settings`: por escaneo 20 llamadas y 500 000 tokens; por día 40 y 1 000 000 (hora de Lima).
- `POST /api/scan/estimate` da el rango y un identificador de un solo uso (10 min); escanear sin él da 409.

## Pendiente (Walter aprueba cada fase)
Fase 3: 3–4 escaneos de temas distintos leyendo la evidencia (`docs/fase3/`). Fase 4: modo Videos, en rama nueva.
Reddit: espera aprobación externa. Corte de la base al contenedor `sentra-pg`: espera a David.
