# La pipeline antigua de Reddit: qué se retiró y qué queda (C2)

Antes del escaneo multifuente y del juez, SENTRA tenía una pipeline propia:
un grafo LangGraph escaneaba un subreddit, analizaba cada post con un NLI
heurístico, agrupaba las señales en clusters, calculaba un Top N y lo
guardaba en PostgreSQL y en una tabla LanceDB de señales. Encima había un
tablero, un feed, una ficha con Blueprint, Arquitecto Gemini y PDF, y la
vista «Control del pipeline».

Con el Radar alimentado por el juez (D-C2) nada de eso tenía ya quien lo
usara. Se retiró en la misión «cerrar pendientes + Fase 4», rama
`feat/cierre-y-documentos`. Las decisiones del usuario son D-C2 a D-C5, en
`tasks/SPEC-cierre-y-documentos.md`.

## Retirado

**Interfaz** (daa91b6):
- tablero de oportunidades, feed de señales y Top 6 antiguo;
- ficha de oportunidad, con Blueprint, Arquitecto, PDF y traducción de citas;
- «Control del pipeline»;
- el interruptor demo/Reddit y las credenciales de Reddit en Ajustes;
- el estado del escáner de Reddit y el aviso del NLI en la salud (e84eb74).

**Rust:** 17 comandos IPC y los módulos `radar`, `blueprint` y `document`.
`architect` se quedó en `gemini` (clave y modelos). Hay un guardia:
`tests/test_superficie_ipc.py` impide que vuelvan.

**Sidecar** (e84eb74): `/api/scan`, `/api/scan/stream`,
`/api/config/mode`, `/api/credentials*`, `/api/blueprint`,
`/api/document/pdf`, `/api/architect/generate` y `/api/translate`. La
superficie queda fijada en `tests/test_sidecar.py` (TestSurface).

**Python:**
- `core/orchestration/`: `graph`, `pipeline`, `state`, `aggregation`,
  `top_n`, `source_status` y `mcp_server` (el servidor MCP del grafo).
- `core/storage/hybrid_search.py`: la búsqueda BM25 + densa sobre señales.
  La nueva busca sobre la evidencia (D-C4, `core/evidence/search.py`).
- `core/intelligence/gemini_architect.py` y `translator.py`.
- `core/ingestion/synthetic.py`, el corpus de demostración del grafo.
- En `PostgresStore`, la escritura y la lectura antiguas: `persist_state`,
  `save_raw_posts`, `save_raw_comments`, `save_signal`, `save_opportunity`,
  `save_cluster`, la asignación de identidades, `ensure_subreddit`,
  `fetch_*`, `search_posts`, `count_posts` y los mapeos y normalizadores
  a los ENUM antiguos.
- Dependencias: `langgraph`, `mcp` y `rank-bm25`.

## Se queda, y por qué

- **Las tablas y vistas antiguas, sin escrituras.** La misión prohíbe
  borrarlas y sus datos siguen siendo consultables con SQL. Son `raw_posts`,
  `raw_comments`, `analyzed_signals`, `opportunity_clusters`,
  `opportunity_cluster_signals`, `jtbd_opportunities`, `cluster_validations`,
  `subreddits`, `v_radar_feed`, `v_opportunity_board` y
  `v_subreddit_health`, más la tabla LanceDB de señales. `pipeline_runs`
  sigue en uso: el escaneo multifuente abre y cierra ahí sus ejecuciones.
- **`core/ingestion` (cliente OAuth de Reddit, filtro, normalizador,
  paginación) y `core/intelligence` (NLI, JTBD, puntuación temporal,
  clustering por temas).** Los usan `scripts/demo_ingestion.py` y
  `scripts/demo_intelligence.py`, que la misión conserva (D5). Además, el
  adaptador `core/sources/reddit.py` reutiliza la autenticación, los errores
  y el User-Agent de `core/ingestion`. Ejecutar los scripts contra Reddit
  sigue sujeto a R7: cero llamadas en esta misión.
- **`core/storage/lancedb_store.py`.** `core/evidence/vectors.py` usa su
  resolución de ruta y su escape SQL, y `scripts/backfill_lancedb_source.py`
  usa su clase.
- **`core/storage/identity.py`.** El juez lo usa para la identidad estable de
  cada oportunidad (D-G).
- **`core/intelligence/blueprint.py` y `core/documents/`
  (`model`, `pdf_report`).** Se quedan hasta la Fase E: el PDF con fuente
  incrustada (tildes, ñ), la marca de agua y el índice se reutilizan para el
  dossier y el plan. Lo que la Fase E no use se retira allí.
- **`GeminiProvider.stream_text`, `generate_text` y `ping`.** Forman parte
  del contrato del proveedor de LLM (`core/llm/base.py`), no de la pipeline.
  Hoy nadie las llama, y sus pruebas de robustez las ejercitan directamente.

## Cómo encontrar lo antiguo

Todo lo retirado está en el historial de git, antes de daa91b6. Los datos
siguen en el esquema `radar` de PostgreSQL. Por ejemplo, las lecturas de un
problema:
`SELECT * FROM radar.opportunity_clusters WHERE cluster_key = '…'`.
