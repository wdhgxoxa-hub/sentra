# Tareas: Estabilizacion + Cierre de Fase 4

## Tarea 1: Control de versiones
- [x] `git init`, `.gitignore` exhaustivo, commit inicial de Fases 1-3
- Verificado: commit 40e65b0, 41 archivos, `repos/` fuera del indice

## Tarea 2: Tests de storage en ROJO (TDD)
- [x] `tests/__init__.py`
- [x] `tests/test_storage.py`
- Verificado: rojo inicial por ImportError de la API inexistente; 53 tests en verde al cierre

## Tarea 3: API publica de `core/storage`
- [x] `core/storage/__init__.py` con `__all__` de 15 nombres
- Verificado: `TestPublicApi` comprueba cada nombre exportado

## Tarea 4: Escape SQL
- [x] `_sql_literal` + uso en `get_by_id`, `delete_by_id` y `filter_ids`
- Verificado: payload `' OR '1'='1` no recupera ni borra nada; `o'brien` sigue siendo una clave valida

## Tarea 5: Ruta configurable
- [x] `resolve_db_path`: argumento > `RIR_LANCEDB_PATH` > `<raiz>/data/lancedb`
- Verificado: test de regresion que falla si vuelve a aparecer un hardcode de unidad

## Checkpoint B
- [x] Suite acumulada completa en verde: 85 tests

## Tarea 6: Embeddings reales
- [x] `core/storage/embeddings.py`: `FastEmbedEmbedder` (BAAI/bge-small-en-v1.5, 384 dims)
- [x] `HashEmbedder` degradado a emergencia: `get_embedder` lanza `EmbeddingError` salvo opt-in explicito
- Verificado: "billing exports are broken" recupera "I cannot export my invoices to a CSV file"
  en primera posicion sin compartir vocabulario

## Tarea 7: Verificacion NLI zero-shot
- [x] Estado real documentado

## Checkpoint C
- [x] Review multi-eje aplicada (proyeccion de columna, filtro acotado, imports huerfanos)
- [x] Commit 2

---

# Fase 5: Orquestacion, integracion E2E y MCP

## Tarea 8: Estado canonico y puente entre capas
- [x] `core/orchestration/state.py`: `RadarState` con reductores + `signal_to_record`
- Verificado: 7 tests sobre el mapeo AnalyzedSignal -> OpportunityRecord

## Tarea 9: Los cinco nodos del grafo
- [x] `graph.py`: fetch / filter / intelligence / storage / quality_gate
- [x] Dependencias inyectadas (`RadarDependencies`): ningun test toca la red
- [x] Resiliencia por nodo: los fallos van a `state["errors"]`, no tumban la ejecucion
- Verificado: 22 tests, incluidos fetcher roto y almacen roto

## Tarea 10: Ciclo controlado
- [x] Arista condicional desde el gate con tope `max_cycles`
- Verificado: cicla al no alcanzar el objetivo, para por objetivo, por tope y por fuente agotada

## Tarea 11: Runner de alto nivel
- [x] `pipeline.py`: `RadarPipeline.run` / `.arun` + `RedditFetcher`
- Verificado: 4 tests; demo E2E con embeddings reales de fastembed

## Tarea 12: Servidor MCP
- [x] `mcp_server.py`: `scan_subreddit`, `search_pain_points`, `get_opportunity_details`
- Verificado: handshake JSON-RPC real por stdio contra `python -m core.orchestration.mcp_server`,
  protocolo 2024-11-05, las 3 herramientas publicadas con sus firmas

## Checkpoint E
- [x] Suite acumulada completa: 140 tests en verde
- [x] Review multi-eje aplicada (indice lexico ciclico, parametro sombreado)
- [x] Commit 3

---

# Deuda tecnica abierta

## D1: NLI zero-shot de Fase 3 corriendo en modo heuristico  (PRIORIDAD ALTA)
`transformers` y `torch` estan AUSENTES, por lo que `ZeroShotNLIClassifier.hf_pipeline`
es `None` y la clasificacion de intencion de compra, severidad del dolor y sentimiento
se resuelve siempre por reglas, no por inferencia NLI.
Los 3 tests de `TestZeroShotNLIClassifier` validan el fallback, no el modelo.
Coste de cerrarla: ~2,5 GB (PyTorch) + ~1,6 GB (facebook/bart-large-mnli).
Decision del usuario el 2026-09-20: verificar y documentar ahora, instalar mas adelante.

## D2: El fallback por hash sigue siendo alcanzable
`LanceDBStore(allow_hash_fallback=True)` permite arrancar sin proveedor semantico.
Es deliberado (continuidad operativa), pero emite un WARNING y nunca se activa solo.
Revisar si conviene prohibirlo del todo en produccion.

## D3: BM25 sin stemming
La rama lexica no reduce a raiz: "exports" no casa con "export". Es la rama densa
la que cubre ese caso, pero conviene evaluar un stemmer si el corpus crece.

## D4: El modelo de embeddings es monolingue (ingles)
BAAI/bge-small-en-v1.5 esta entrenado en ingles. Si el radar pasa a cubrir
subreddits en otras lenguas, migrar a un modelo multilingue y reindexar.

## D5: El fetcher real no expone cursor, asi que el grafo no cicla en produccion
`fetch_subreddit_posts` encapsula el cursor `after` y no lo devuelve, de modo que
`RedditFetcher` informa siempre `next_cursor=None`. El ciclo del grafo funciona y
esta probado con fetchers inyectados, pero contra Reddit real solo dara una vuelta.
Correccion: que la Fase 2 acepte un `after` inicial y devuelva el cursor final.

## D6: El corte de 60 puntos es inalcanzable para una senal individual
El scoring de Fase 3 esta calibrado para oportunidades AGREGADAS: `spread` y
`frequency` miden difusion entre comunidades y repeticion. Una senal suelta los
tiene en el minimo (0.2 cada uno), con lo que su techo real ronda los 25-45 puntos.
El corte por defecto se mantiene en 60.0 como se especifico, pero `min_score` es
ahora configurable en `build_graph`, `RadarPipeline` y `create_server`.
Decision pendiente: bajar el corte, o aplicar el gate sobre clusters agregados
en lugar de senales individuales (lo segundo es lo que el scoring presupone).

## D7: El filtro de dolor busca terminos de dominio, no frustracion
Las 33 expresiones de `PAIN_POINT_KEYWORDS` son terminos de negocio ('manual',
'invoice', 'automate'). Un post que dice "this is broken and I am stuck" sin
vocabulario de dominio se descarta. Es deliberado para precision, pero conviene
medir cuanto recall cuesta.

## D8: La ingesta real no se ha ejecutado contra Reddit
Todo el pipeline esta verificado con fetchers inyectados. La conexion real de
`RedditIngestionClient` contra reddit.com no se ha ejercitado en esta sesion.
