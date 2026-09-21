# Plan de Implementación: Estabilización + Cierre de Fase 4

## Overview
Tras un apagón se audita el proyecto y se detecta: ausencia total de control de
versiones, una Fase 4 (`core/storage`) escrita a medias y sin pruebas, y dos
placebos (embedder MD5 no semántico, NLI zero-shot siempre en fallback).
Este plan estabiliza el entorno, cierra la Fase 4 formalmente y sustituye el
embedder placebo por embeddings reales.

## Architecture Decisions
- **Commit 1 = Fases 1-3 únicamente.** `core/storage` queda fuera del commit
  inicial para que el historial refleje "base estable" vs "Fase 4 validada".
- **SQL seguro por escape de comillas**, no por parámetros: la API de filtros de
  LanceDB (`.where()`) recibe una cadena SQL y no expone binding de parámetros.
- **Ruta configurable en cascada**: argumento explícito > variable de entorno
  `RIR_LANCEDB_PATH` > `<raíz del proyecto>/data/lancedb`. Se elimina el
  hardcode `F:\`.
- **Embeddings por proveedor enchufable** con degradación explícita: el fallback
  MD5 deja de ser silencioso y debe pedirse a propósito.

## Task List

### Fase A: Control de versiones
- [ ] Tarea 1: `git init` + `.gitignore` exhaustivo + commit inicial (Fases 1-3)

### Checkpoint A
- [ ] `git status` limpio salvo `core/storage/` (Fase 4, aún sin commitear)
- [ ] `repos/` (57 clones de terceros) fuera del índice

### Fase B: Cierre de Fase 4
- [ ] Tarea 2: `tests/__init__.py` + `tests/test_storage.py` en ROJO (TDD)
- [ ] Tarea 3: `core/storage/__init__.py` con API pública explícita
- [ ] Tarea 4: `lancedb_store.py` — escape SQL en `get_by_id`/`delete_by_id`
- [ ] Tarea 5: `lancedb_store.py` — ruta configurable, sin hardcode `F:\`

### Checkpoint B
- [ ] `tests/test_storage.py` en VERDE
- [ ] Suite acumulada (ingestion + intelligence + storage) en VERDE

### Fase C: Eliminar placebos
- [ ] Tarea 6: proveedor de embeddings reales + MD5 degradado a emergencia explícita
- [ ] Tarea 7: verificación documentada de transformers/PyTorch para el NLI

### Checkpoint C
- [ ] Suite completa en VERDE con embeddings reales
- [ ] Review multi-eje + commit 2

## Risks and Mitigations
| Riesgo | Impacto | Mitigación |
|---|---|---|
| Cambio de dimensión del vector (128 -> 384/768) invalida datos persistidos | Medio | `data/` está ignorado y solo contenía una tabla de prueba; la dimensión pasa a derivarse del proveedor |
| `sentence-transformers` arrastra PyTorch (~2.5 GB) | Medio | Preferir un proveedor ONNX sin torch |
| Ollama requiere un servicio vivo en los tests | Alto | Los tests nunca dependen de red: usan un embedder determinista inyectado |
| Escape SQL insuficiente ante comillas | Alto | Test explícito con `id` malicioso que intenta romper el `where` |

## Open Questions
- Proveedor de embeddings reales a adoptar (pendiente de decisión del usuario).

---

# Implementación Fase 5: Orquestación, Integración E2E y MCP

## Overview
Cierra el ciclo funcional: las tres capas (ingestion, intelligence, storage)
dejan de ser islas y pasan a ejecutarse como un pipeline unico, orquestado por
una maquina de estados de LangGraph y expuesto a clientes IA por MCP stdio.

## Architecture Decisions
- **Inyeccion de dependencias en el grafo.** Los nodos se construyen sobre un
  `RadarDependencies` (fetcher, filtro, motor, almacen). Sin esto el grafo solo
  seria testeable con red real contra Reddit.
- **El fetcher es un callable, no el cliente.** `RedditIngestionClient` es
  asincrono y golpea la red; el grafo recibe una funcion
  `(subreddit, limit, sort, cursor) -> (items, next_cursor)`. El adaptador real
  vive en `pipeline.py` y los tests inyectan uno falso.
- **`signal_to_record` vive en `state.py`.** Es la conversion de frontera entre
  el modelo analitico (`AnalyzedSignal`) y el de persistencia
  (`OpportunityRecord`), junto al resto de estructuras que fluyen por el grafo.
- **Ciclo controlado por `QualityGateNode`.** Si no se alcanza el objetivo de
  oportunidades cualificadas y queda cursor, el grafo vuelve a `FetchNode`.
  `max_cycles` corta el bucle siempre.
- **Resiliencia por nodo.** Cada nodo captura sus excepciones y las acumula en
  `state["errors"]`; un fallo de red no tumba la ejecucion entera.
- **El orden Fetch -> Filter -> Intelligence -> Storage -> QualityGate es el
  especificado.** Implica persistir tambien lo que no supera el corte; el gate
  decide lo que se *reporta*, no lo que se *guarda*.

## Task List

### Fase D: Puente e infraestructura del grafo
- [ ] Tarea 8: `state.py` — `RadarState` + `signal_to_record`
- [ ] Tarea 9: `graph.py` — los cinco nodos con dependencias inyectadas
- [ ] Tarea 10: `graph.py` — arista condicional ciclica + tope `max_cycles`

### Checkpoint D
- [ ] Grafo compila y recorre el flujo con dependencias falsas

### Fase E: Ejecucion y exposicion
- [ ] Tarea 11: `pipeline.py` — runner sincrono/asincrono + adaptador real de ingesta
- [ ] Tarea 12: `mcp_server.py` — `scan_subreddit`, `search_pain_points`, `get_opportunity_details`

### Checkpoint E
- [ ] Suite completa en verde
- [ ] Review multi-eje + commit

## Risks and Mitigations
| Riesgo | Impacto | Mitigación |
|---|---|---|
| Los tests tocan la red de Reddit | Alto | El fetcher siempre se inyecta; ningun test instancia el cliente real |
| Bucle infinito en el grafo ciclico | Alto | `max_cycles` y avance obligatorio de cursor |
| El NLI sigue en fallback heuristico | Medio | Documentado (deuda D1); el pipeline no lo disimula |
| `opportunity_score` en dos escalas | Medio | Se fija 0-100, la de `TemporalScoreBreakdown.final_score` |
