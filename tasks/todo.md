# Tareas: Estabilización + Cierre de Fase 4

## Tarea 1: Control de versiones
- [ ] `git init`, `.gitignore` exhaustivo, commit inicial de Fases 1-3
- Verificación: `git log --stat` muestra la base; `repos/` no aparece

## Tarea 2: Tests de storage en ROJO (TDD)
- [ ] `tests/__init__.py`
- [ ] `tests/test_storage.py`: inserción, get por id, borrado, búsqueda vectorial, RRF híbrido, escape SQL, ruta configurable
- Verificación: los tests nuevos fallan antes de tocar el código

## Tarea 3: API pública de `core/storage`
- [ ] `core/storage/__init__.py` con `__all__`
- Verificación: `from core.storage import LanceDBStore, HybridSearchEngine`

## Tarea 4: Escape SQL
- [ ] `get_by_id` y `delete_by_id` sin interpolación cruda
- Verificación: test con id `x' OR '1'='1`

## Tarea 5: Ruta configurable
- [ ] argumento > `RIR_LANCEDB_PATH` > `<raíz>/data/lancedb`
- Verificación: test que fija la env var y comprueba la ruta resuelta

## Checkpoint B
- [ ] Suite acumulada completa en verde

## Tarea 6: Embeddings reales
- [ ] Proveedor real + MD5 solo bajo petición explícita
- Verificación: dos textos sinónimos puntúan por encima de dos no relacionados

## Tarea 7: Verificación NLI zero-shot
- [ ] Estado real de transformers/PyTorch documentado

## Checkpoint C
- [ ] Review + commit 2 + reporte final
