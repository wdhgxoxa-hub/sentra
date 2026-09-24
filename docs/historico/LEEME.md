# Documentos históricos

Nada de esta carpeta describe SENTRA tal como es hoy. Se conservan por
trazabilidad (AUD2-017, decisión DP11 A del 2026-09-24).

El proyecto empezó como una biblioteca de 57 repositorios de terceros
clonados para estudiarlos (1,6 GB). SENTRA no los usa: los clones se movieron
a `F:\archivo_sentra\repos`, fuera del proyecto, junto con el índice que los
describía (`F:\archivo_sentra\INDEX.md`).

| Documento | Qué era |
|---|---|
| `SPECIFICATION.md` | Especificación de la biblioteca de repositorios clonados. |
| `PLAN.md` | Plan de tareas de esa biblioteca. |
| `MATRIZ_SELECCION_BEST_OF_BREED.md` | Selección técnica sobre los 57 clones (fase 1). |
| `SPEC-blueprint.md` | Especificación del plano inicial, anterior a la multifuente. |
| `ARQUITECTURA_POSTGRES_Y_FRONTEND.md` | Esquema y frontend de la fase 6: dice que no hay código de interfaz y usa LanceDB de 384 dimensiones; ambas cosas cambiaron. |

Lo vigente está en el README, en `tasks/SPEC-cierre-y-documentos.md`,
`tasks/SPEC-multifuente.md`, `docs/pipeline-antigua.md` y `docs/proceso.md`.

Los scripts de la biblioteca (`clone_manager.py`, `clone_batch2.py`,
`generate_index.py`, `repo_analyzer.py`, `verify_integrity.py`, `test_radar.py`,
`update_results.py`, `print_report.py`, `test_candidates.py`) y
`logs/repo_catalog.json` se retiraron del repositorio a petición del usuario;
hay copia idéntica en `F:\archivo_sentra\scripts` y siguen en el historial de git.
