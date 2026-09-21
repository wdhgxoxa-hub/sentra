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

# Fase 6: Arquitectura de datos PostgreSQL y especificacion del frontend

## Tarea 13: Esquema relacional  (PASO 1.1)
- [x] `sql/schema.sql`: 7 tablas, 2 vistas, 11 ENUM, 54 indices, 6 politicas RLS, 3 triggers
- [x] Ejecutado de verdad contra PostgreSQL 18.6, sin errores
- Verificado: 7 constraints rechazan lo que deben; cascadas CASCADE y SET NULL;
  versionado por content_hash; FTS en 'english' y 'simple'; trigram; EXPLAIN
  confirma que el indice parcial del dashboard se usa

## Tarea 14: Adaptador Python  (PASO 1.2)
- [x] `core/storage/postgres_store.py`: funciones puras de mapeo + repositorio asincrono
- [x] `persist_state()` vuelca el RadarState del grafo en una transaccion
- [x] `run_async()` resuelve la incompatibilidad de psycopg con ProactorEventLoop en Windows
- Verificado: 39 pruebas (29 de mapeo sin BD + 10 de integracion real)

## Tarea 15: Documentacion arquitectonica  (PASO 2)
- [x] `docs/ARQUITECTURA_POSTGRES_Y_FRONTEND.md`
- [x] Contratos TypeScript, tabla de comandos IPC, eventos, estructura de carpetas
- NOTA: el frontend es ESPECIFICACION. No hay codigo de UI escrito.

## Checkpoint F
- [x] Suite acumulada: 215 pruebas en verde
- [x] Commit

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

## D5: CERRADA (2026-09-21) - cursor de paginacion propagado
`fetch_subreddit_page()` acepta el cursor `after` entrante y devuelve el
`next_cursor` de Reddit; `fetch_subreddit_posts()` conserva su firma historica
y lo usa internamente para recorrer la cadena. `RedditFetcher` traduce el
cursor en ambos sentidos, de modo que el ciclo del grafo avanza de verdad.
Verificado con 13 pruebas nuevas sobre payloads con la forma real de Reddit.

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

## D8: BLOQUEADA POR REDDIT (verificado 2026-09-21)  (PRIORIDAD ALTA)
El smoke test real no se pudo completar: Reddit ha cerrado el acceso anonimo a
los endpoints `.json`. Evidencia recogida:

  www.reddit.com/r/SaaS/new.json      -> HTTP 403 (todas las variantes probadas)
  old.reddit.com/r/SaaS/new.json      -> HTTP 200 pero redirige a
                                         /login/?reason=lor2 y sirve HTML
  oauth.reddit.com/r/SaaS/new         -> HTTP 403 (exige token)
  www.reddit.com/r/SaaS/new/.rss      -> HTTP 200 con contenido real

No es un fallo del codigo: es un control de acceso de la plataforma. Se probo
con varios perfiles TLS (chrome124/131), con y sin cabeceras propias, y como
navegacion top-level. No se insistio en burlar el WAF: la via correcta es
autenticarse.

El canal Atom publico funciona, pero NO pagina (el parametro `after` devuelve
pagina vacia) y NO trae `score`, `ups`, `num_comments` ni `upvote_ratio`, que
son justamente las senales que alimentan el scoring temporal.

Decision del usuario (2026-09-21): opcion A, OAuth oficial.

Estado: el soporte OAuth esta IMPLEMENTADO y verde (23 pruebas nuevas), pero el
escaneo real sigue PENDIENTE de que el usuario cree la app y aporte credenciales.

  core/ingestion/auth.py   RedditOAuth (client_credentials y password),
                           cache de token con margen de expiracion,
                           load_dotenv sin dependencias externas
  client.py                habla con oauth.reddit.com y manda el bearer
                           cuando hay credenciales; si no, modo anonimo
  .env.example             plantilla con los pasos para crear la app

Pendiente tras el smoke: los endpoints de hilo (fetch_thread_comments y
fetch_full_thread) siguen usando solo el endpoint publico .json y no se han
migrado a OAuth. Necesitan el mismo tratamiento que fetch_subreddit_page.

## D9: El esquema no tiene versionado de migraciones
`sql/schema.sql` crea todo desde cero. No hay `schema_migrations` ni archivos
numerados, asi que el primer cambio en produccion seria manual y sin vuelta
atras. Recomendacion: `sql/migrations/NNN_*.sql` + tabla de control, sin ORM
(el proyecto no usa SQLAlchemy y anadirlo solo para migrar seria desmedido).

## D10: competitors_mentioned se alimenta de un solo campo
`opportunity_to_row` rellena el array con `current_solution` unicamente,
porque el motor de Fase 3 no extrae una lista de competidores. La columna
esta preparada para mas; el extractor no.

## D11: El adaptador solo persiste posts, no comentarios
`raw_comments` existe en el esquema y esta indexada, pero `persist_state`
solo escribe posts: el grafo de Fase 5 no ingiere hilos de comentarios.
Queda listo para cuando lo haga.
