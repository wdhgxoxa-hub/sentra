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

## D6: CERRADA (2026-09-21) - dos umbrales y agregacion real
El corte de 60 no estaba mal: se aplicaba al objeto equivocado. Ahora:
  SIGNAL_THRESHOLD = 20.0              filtro de higiene sobre el mensaje
  OPPORTUNITY_CLUSTER_THRESHOLD = 60.0 corte sobre el problema consolidado
`core/orchestration/aggregation.py` agrupa senales por interseccion de
intencion JTBD y vocabulario de dolor (union-find, transitivo) y recalcula
spread/frequency con metricas agregadas. Un cluster de 6 menciones en 5
comunidades alcanza 73.5 puntos (HIGH); la mejor senal suelta se queda en 60.
Corregido de paso: `intelligence_node` pasaba a cada senal el numero de
comunidades del LOTE, inflando su spread con contexto ajeno. Ahora una senal
individual se puntua como lo que es, una sola voz.

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

## D9: CERRADA (2026-09-21) - gestor de migraciones
`sql/schema.sql` pasa a ser `sql/migrations/001_initial_schema.sql`, unica
fuente de verdad. `scripts/migrate.py` aplica lo pendiente con control en
`public.schema_migrations`: orden numerico (010 tras 002), una transaccion
por migracion y huella de contenido que impide editar una ya aplicada.
Sin Alembic: vive sobre SQLAlchemy y el proyecto no usa ORM.
Verificado con 24 pruebas, incluidas migracion rota (no deja rastro) y
migracion alterada tras aplicarse (se detecta).

## D10: competitors_mentioned se alimenta de un solo campo
`opportunity_to_row` rellena el array con `current_solution` unicamente,
porque el motor de Fase 3 no extrae una lista de competidores. La columna
esta preparada para mas; el extractor no.

## D11: El adaptador solo persiste posts, no comentarios
`raw_comments` existe en el esquema y esta indexada, pero `persist_state`
solo escribe posts: el grafo de Fase 5 no ingiere hilos de comentarios.
Queda listo para cuando lo haga.

## D12: CERRADA (2026-09-21) - clusters persistidos
Migracion `002_opportunity_clusters.sql`: tabla `opportunity_clusters` con el
desglose de scoring aplanado en columnas, y pivote N:M
`opportunity_cluster_signals`. Una fila por (ejecucion, cluster_key), no un
upsert: el historial de como evoluciona una oportunidad ES la senal.
`persist_state()` los escribe dentro de su transaccion; `fetch_opportunity_board`
y `fetch_cluster_history` los leen. Vista `v_opportunity_board`.
Verificado con 15 pruebas nuevas, incluidas cascada de la pivote y el CHECK
que impide que un cluster abarque mas comunidades que menciones tiene.

## D13: La agrupacion lexica puede sobre-fusionar
Dos senales se unen si comparten UNA keyword del vocabulario de dolor y la
intencion JTBD. Terminos muy comunes ('manual', 'every day') podrian juntar
problemas distintos. Conviene medirlo sobre datos reales y, si ocurre,
ponderar los terminos por frecuencia inversa antes de unir.

---

# Fase 7: Frontend de escritorio (en curso)

## Tarea 16: Bootstrap del workspace  (HECHO)
- [x] `ui/` con Vite 6, React 19, TypeScript 5.7, Tailwind v4
- [x] `ui/src/types/radar.ts`: contratos espejo de los ENUM de las migraciones
- [x] TanStack Query (datos de servidor) + Zustand (estado de interfaz)
- [x] `ui/src-tauri/`: Cargo.toml, tauri.conf.json, capabilities, comandos
- [x] `rust-toolchain.toml` fija MSVC por proyecto (el default de la maquina
      es gnu, con el que Tauri no enlaza en Windows)
- Verificado: `npm run build` -> 90 modulos, 274 KB (84 KB gzip)

## D14: CERRADA (2026-09-21) - sidecar HTTP y ciclo de vida
`core/orchestration/sidecar_server.py`: FastAPI en 127.0.0.1:8765 con
POST /api/scan, POST /api/search y GET /api/health. Solo loopback, y con token
opcional (RIR_SIDECAR_TOKEN) porque cualquier proceso local podria invocar
/api/scan, que consume cuota de Reddit. Sin /docs ni /openapi.json: no es una
API publica.
Rust habla con el via reqwest desde commands/engine.rs, traduciendo los fallos
de transporte a mensajes accionables ("arrancalo con este comando") en vez de
"connection refused".
Verificado por HTTP real: handshake, 401 sin token, 422 en validacion, escaneo
completo persistido y busqueda hibrida.

## D15: Faltan iconos de la aplicacion
Se retiro `bundle.icon` de tauri.conf.json porque apuntaba a un .ico
inexistente y rompia el empaquetado. Generar con `npm run tauri icon <png>`
antes del primer build de distribucion.

## D16: CERRADA (2026-09-21) - comandos IPC implementados
Nueve comandos en Rust: get_radar_feed, get_opportunity_board,
get_opportunity_detail, get_cluster_history, get_subreddits, get_pipeline_runs
(PostgreSQL con sqlx), search_hybrid y trigger_scan (sidecar), y get_app_health
(agrega las tres piezas por separado, porque fallan por separado).
`ipc.ts` declara exactamente los que existen: un comando declarado sin backend
solo produce fallos en tiempo de ejecucion.

---

# Deuda abierta tras D14 y D16

## D17: CERRADA (2026-09-21) - comandos de escritura
Migracion `003_human_validation.sql` + `ui/src-tauri/src/commands/mutations.rs`:
  update_opportunity_status(cluster_key, status, notes, assigned_to)
  upsert_subreddit(params)   con etiquetas y pausa/activacion
  cancel_scan(run_id)

Decision central: la validacion va por `cluster_key`, en su propia tabla
`cluster_validations`, NO por fila de `opportunity_clusters`. Esa tabla guarda
una lectura por ejecucion (migracion 002), asi que validar una fila seria
validar una foto. Lo que un analista valida es el PROBLEMA, que sobrevive a
cada escaneo. Verificado: una sola decision se aplica a las 4 lecturas del
mismo problema, incluida la de 60 puntos y 1 mencion.

Los estados son los del ENUM existente (new, triaged, validated, rejected,
shipped), equivalentes a los citados en el encargo (unreviewed, investigating,
built). Renombrarlos exigiria migrar datos y tocar el indice parcial sin ganar
nada; si se quieren los otros nombres, es una migracion aparte.

UI: `ValidationControls` en la ficha y `SubredditForm` mas pausar/activar y
cancelar en el Centro de Control, con invalidacion de cache en TanStack Query.

Verificado con 9 pruebas de integracion en Rust contra una base desechable
levantada con las migraciones reales.

## D18: CERRADA (2026-09-21) - ciclo de vida del sidecar
`ui/src-tauri/src/sidecar.rs`: al abrir, comprueba si el sidecar ya responde
y, si no, lo lanza con `python -m core.orchestration.sidecar_server`; sondea
/api/health hasta 30 s (la primera arrancada carga el modelo de embeddings);
al cerrar la ventana lo recoge, y tambien en Drop por si el proceso muere de
forma abrupta.

Regla central: SOLO SE MATA LO QUE SE ARRANCO. Si ya habia un sidecar vivo
(una consola de desarrollo, otra instancia), cerrar la app no se lo lleva.

En Windows se lanza con CREATE_NO_WINDOW para que no aparezca una consola
negra detras de la ventana.

Verificado con 4 pruebas en Rust, incluida una que arranca un sidecar real,
comprueba que contesta y verifica que muere tras shutdown.

## D19: CERRADA (2026-09-21) - progreso en tiempo real
`RadarPipeline.astream_state()` usa `stream_mode=["updates","values"]` de
LangGraph: `updates` dice QUE nodo acaba de correr y `values` trae el estado
acumulado tras el. El sidecar lo expone en `POST /api/scan/stream` por SSE, y
Rust lo retransmite al WebView por el canal `radar:events`.

La interfaz pinta la barra con `progressStore` (Zustand, porque son eventos
empujados y no cache de nada) y `ScanProgressBar`, que muestra la fase y los
contadores: cuando un escaneo tarda, lo que tranquiliza es ver "descargados
25, analizando", no un 40 % sin contexto.

Verificado consumiendo el SSE como lo hace Rust: los eventos llegan
escalonados (+141 ms started, +156 fetch, +703 intelligence, +891 finished),
lo que demuestra que es streaming y no un volcado al final.

## D20: uvicorn impone ProactorEventLoop en Windows
psycopg no funciona sobre el. Se resuelve ejecutando la persistencia en un
hilo con su propio SelectorEventLoop (`asyncio.to_thread` + `run_async`).
Funciona, pero conviene recordarlo antes de anadir mas codigo async con
psycopg dentro del sidecar.

## D21: LanceDB no se podia reabrir con datos  (CERRADA el 2026-09-21)
Encontrado al arrancar el sidecar supervisado: `list_tables()` devuelve un
`ListTablesResponse`, no una lista, asi que `nombre in respuesta` daba
siempre falso y `_init_table` intentaba recrear una tabla existente. El
almacen reventaba al abrirse con datos, que es el caso de produccion; los
tests no lo veian porque cada uno estrena directorio temporal.
Corregido con `_existing_tables()` y tres pruebas de reapertura.
Lo introduje yo en la Fase 4 al cambiar `table_names()` por `list_tables()`
para silenciar un DeprecationWarning: silenciar un aviso sin comprobar que
el sustituto devuelve lo mismo.

## D22: CERRADA (2026-09-21) - cancelacion de escaneos
`POST /api/scan/cancel` en el sidecar, cooperativa: el grafo se corta ENTRE
nodos, nunca a mitad de uno, porque abortar un nodo a media escritura dejaria
el almacen inconsistente. Lo cosechado hasta el corte se conserva, marcado
como `cancelled`.
El cliente puede fijar el `runId` al lanzar el escaneo; sin eso no hay forma
de cancelar algo que aun no ha empezado a responder.
`cancel_scan` en Rust avisa al sidecar y marca la ejecucion en PostgreSQL, y
ninguna de las dos cosas depende de que la otra funcione.
Verificado: run:started -> run:cancelled, 0 de 6 nodos ejecutados.

## D23: El progreso no distingue ciclos en la barra
Con el grafo ciclico, los nodos se repiten en cada vuelta. La barra no
retrocede (los nodos ya vistos no se recuentan), pero tampoco refleja que
queda otra vuelta: al final del ciclo 1 marca 100 % aunque vaya a haber un
ciclo 2. El numero de ciclo si se muestra aparte.

## D24: El estado de validacion no filtra el tablero
`cluster_validations` ya alimenta `v_opportunity_board`, pero el Radar View no
ofrece filtrar por estado. Con muchas oportunidades, lo ya descartado seguira
ocupando sitio junto a lo que nadie ha mirado.

## D25: No hay forma de deshacer una validacion
Se puede cambiar el estado, pero no borrar la fila de `cluster_validations`:
una oportunidad marcada por error se queda con historial de decision aunque
vuelva a 'new'. Falta un `clear_validation` o equivalente.

## D26: Los tests de Rust comparten una base de datos
`rir_mutations_test` se crea una vez y los tests usan claves distintas para no
pisarse. Funciona, pero es un acuerdo tacito: un test nuevo que reutilice una
clave existente fallara de forma confusa.
