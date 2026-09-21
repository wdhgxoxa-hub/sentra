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
