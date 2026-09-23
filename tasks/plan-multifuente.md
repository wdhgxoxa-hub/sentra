# Plan: SENTRA multifuente + juez de nichos

Especificación: `tasks/SPEC-multifuente.md`. Rama: `feat/multifuente`.
Nota: `tasks/plan.md` pertenece a un trabajo anterior (21 tareas sin marcar) y no se toca.

## Decisiones de arquitectura

- `LLMProvider` es un protocolo en `core/llm/base.py`, con `GeminiProvider` como
  única implementación. `gemini_client.py` y `gemini_architect.py` pasan a
  usarlo, y el SDK solo se importa en `core/llm/gemini.py`.
- Los modelos se eligen en vivo con `models.list`: por defecto el Flash
  estable 3.x más reciente, y para documentos el Pro más reciente. Si un
  modelo guardado ya no está en la lista, se lanza `LLMModelUnavailable`, con
  traducción es/en.
- Las fuentes son adaptadores async sobre httpx, con dobles `MockTransport`
  construidos a partir de la documentación oficial. El presupuesto se aplica
  por fuente y por escaneo en un solo sitio (`core/sources/budget.py`).
- El juez es código puro sin E/S (`core/judge/`); lo persiste la capa de
  orquestación.
- La migración 009 aplica D-M1 y la 010 el LanceDB de 1024 dimensiones
  (D-M2). Ninguna migración anterior se edita.

## Fase 1 — Motor de IA

- [x] T1.1 Protocolo `LLMProvider`, errores tipados y `UsageRecord` (tokens de entrada, salida y razonamiento, modelo y duración). Test: ningún módulo fuera de `core/llm/` importa `google.genai` (test AST).
- [x] T1.2 `GeminiProvider.list_models()` y la elección del modelo por defecto, con criterio documentado. Test: selección con listas simuladas (3.x flash/pro, preview frente a estable, familia 2.5 ausente).
- [x] T1.3 `generate_text`, `stream_text` y `ping` movidos detrás del proveedor, sin perder AUD-020 ni AUD-031. Los tests existentes siguen verdes.
- [x] T1.4 `generate_json(schema)`: salida estructurada nativa, validación Pydantic, un reintento con el error y, si vuelve a fallar, `LLMInvalidJson`.
- [x] T1.5 Presupuesto LLM por escaneo (D-M4). Al agotarse, `LLMBudgetExhausted`, que el escaneo detiene con un motivo tipado. *(El corte del escaneo se engancha en T3.3, donde el escaneo empieza a llamar al LLM.)*
- [x] T1.6 Sidecar y UI: la configuración lista los modelos en vivo; el modelo guardado que desaparece da error traducido; se retira el `gemini-2.5-*` fijo.
- [x] T1.7 Verificación real: 2 llamadas (probar la clave y un `generate_json` corto).
- **Checkpoint F1** ✅ 2026-09-23: 2 llamadas reales (models.list y generate_json con gemini-3.8-flash).

## Fase 2 — Núcleo multifuente

- [x] T2.1 `EvidenceItem`, `SearchQuery` y `author_hash` con sal local, generada una vez y guardada con el mecanismo seguro de `.env`.
- [x] T2.2 Migración 009 (D-M1), probada en una base desechable: tablas nuevas, copia de raw_* con hash, autores antiguos hasheados, vistas reescritas. *(Mientras el escaneo multifuente no la sustituya, la pipeline de Reddit sigue escribiendo sus tablas antiguas, ya con autores hasheados, y además copia a `evidence_items`. Esas escrituras antiguas se retiran en T2.7.)*
- [ ] T2.3 Almacén: upsert idempotente de `evidence_items` y LanceDB 1024-d con `source` e id global (D-M2 y migración 010).
- [ ] T2.4 Contrato de adaptador, errores comunes, presupuesto y cabeceras de cuota (Retry-After, X-RateLimit-*).
- [ ] T2.5 Registro de fuentes, `sources_state` y estados verificados; modo comercial.
- [ ] T2.6 Perfil de escaneo, biblioteca de frases v1 (es/en) y modo descubrimiento.
- [ ] T2.7 Escaneo paralelo por fuente: el fallo de una no detiene a las demás. Persistencia y SSE por fuente.
- [ ] T2.8 Deduplicación: huella normalizada más similitud de embeddings con un umbral con nombre.
- [ ] T2.9 UI: sección «Fuentes», resumen en la barra lateral, progreso por fuente y perfil de escaneo.
- [ ] T2.10–T2.19 Un adaptador por commit, en el orden de la especificación. Cada uno lleva sus dobles oficiales, su tarjeta con «Probar» y su prueba real acotada según R7.
- **Checkpoint F2**: informe.

## Fase 3 — Juez

- [ ] T3.1 Etapa 0: filtro de calidad determinista con motivos. La autopromoción se conserva como señal de competencia.
- [ ] T3.2 Conjunto dorado de al menos 60 ítems (es/en), inventado.
- [ ] T3.3 Etapa 1: etiquetado con `generate_json`, verificación de `evidence_span`, caché por hash, lotes y `undetermined` sin proveedor.
- [ ] T3.4 Etapa 2: clustering con e5-large e identidad D-G.
- [ ] T3.5 Etapa 3: siete dimensiones y pesos v1 versionados (D-M3).
- [ ] T3.6 Etapa 4: ocho compuertas y tabla de veredictos D-M3. Tests: uno CONSTRUIR, uno INVESTIGAR MÁS por compuerta, uno DESCARTAR y el de honestidad.
- [ ] T3.7 Etapa 5: abogado del diablo, que solo baja.
- [ ] T3.8 Persistencia de `niche_verdicts` y el Top 6 ordenado por veredicto (AUD-007).
- [ ] T3.9 UI: mapa de corroboración, panel del juez y abogado del diablo.
- [ ] T3.10 Concordancia real con 20 ítems dorados, dentro del cupo de Gemini.
- **Checkpoint F3**: informe.

## Cierre

Suites y herramientas a 0, instalación limpia, respaldo y migración de la base
real, escaneo real con HN, Stack Exchange y Discourse, release, push y
fast-forward a `main`.

## Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| e5-large pesa 2,24 GB y va lento en CPU | Medio | Se descarga una vez y se cachea; se procesa por lotes; los tests usan un embebedor doble |
| La API de Gemini 3.x difiere en campos (`thinking_level`) | Medio | La elección y la configuración viven en el proveedor; los dobles siguen la forma del SDK instalado |
| Cambios en la autenticación de Stack Exchange (junio de 2025) | Medio | Leer la documentación oficial antes de implementar; sin clave, se usa la cuota anónima |
| La migración 009 rompe vistas o consultas de Rust | Alto | Probarla en una base desechable; los tests de Rust ya se ejecutan de verdad (R-F) |
| El cupo de Gemini (10 llamadas) | Medio | Presupuesto: F1 = 2; concordancia = lotes que cubren 20 ítems; se reserva margen |
