# Plan de implementación: Fase 2 · Interfaz

Especificación: `docs/fase2/PROPUESTA.md`. Principios P1 y P2 en su sección 6; commits en la sección 7.

## Decisiones de arquitectura

- El exe de release se recompila antes de cada commit que toque la UI o el motor, porque el humo prueba ese exe.
- Contratos: cada campo nuevo va en `types/radar.ts`, después `npm run contracts` y `test_contracts.py`. Si hay comando Rust, lleva su test en `contract_tests.rs` y `contract_returns_tests.rs`.
- La lógica de pantalla va en `ui/src/lib/*.ts` como funciones puras con `node --test`. Los componentes solo pintan.
- Modos: `ui/src/modos/`. Los componentes genéricos no importan `JudgeVerdict`.
- Lenguaje llano: la lista de palabras prohibidas vive en un solo sitio (`tests/_lenguaje_llano.py`). El humo la importa.

## Tareas

- [ ] 1. Radar con la última ejecución con nichos
  - Aceptación: con A (INVESTIGAR MÁS) y B vacía posterior, el top es A y `latestRun` es B. Con solo DESCARTAR, nada. Con `runId`, igual que hoy.
  - Verificación: `test_judge_store`, `test_sidecar_judge`, contratos y humo.
- [ ] 2. Estado de los documentos y reutilización sin resolver el modelo
  - Aceptación: status sí/no por tipo e idioma. Exportar algo guardado: 0 llamadas y sin listar modelos.
  - Verificación: `test_documentos_persistentes`, `test_sidecar_documents` y cargo test.
- [ ] 3. Proponer palabras clave (migración 020, Gemini y plantillas)
  - Aceptación: A registra 1 fila con `purpose = palabras_clave`. B sin red y con 0 filas. Tope → 409 o B, según el caso.
  - Verificación: tests nuevos, test de la migración 020 y contratos.
- [ ] 4-6. `lib/cobertura.ts`, `lib/progreso.ts` y `lib/siguientePaso.ts`, con `node --test`.
- [ ] 7. Tokens y guardias 1 y 2
  - Verificación: `test_tema`, `test_lenguaje_llano` y el test de contraste.

### Checkpoint A (tras 1-7)

- Compuerta verde.
- La app sigue como hoy, salvo que el Radar ya no pierde el nicho.

- [ ] 8. Modos y asistente de 3 pasos. Humo: arranca en «Nuevo escaneo», 1 acción principal y guardia 3.
- [ ] 9. Escaneo en curso, resultado y marca D3.
- [ ] 10. Radar y ficha de nicho genéricos.
- [ ] 11. Fuentes, Configuración y Búsqueda. La guardia 1 cubre todo.
- [ ] 12. CLAUDE.md, modo Videos y capturas.

### Checkpoint B (final)

- Capturas del exe de cada pantalla en claro y en oscuro.
- Informe a Walter.
- Sin fusionar ni empujar.

## Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| El humo depende de selectores de la UI actual | Alto | Se actualiza en el mismo commit que cambia la vista; se usan selectores `data-*` estables |
| El tiempo de `tauri build` en cada commit | Medio | Solo se recompila en los commits que tocan UI o motor |
| La migración 020 en la base real | Bajo | Solo amplía el CHECK. Se aplica con D&S libre y se registra |
| La guardia 3 falla por textos del motor (errores, nombres de fuentes) | Medio | Los textos del motor que llegan a la pantalla se traducen en la UI o van en «Ver detalle» |
