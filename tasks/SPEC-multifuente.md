# Spec: SENTRA multifuente + juez de nichos (fases 1 a 3)

Rama: `feat/multifuente` desde `main` (50c5d47).

## Objetivo

SENTRA junta evidencia legítima de dolor de usuarios de todas las plataformas
que tienen API oficial. La cruza entre fuentes y la pasa por un **juez
determinista** que emite un veredicto trazable: **CONSTRUIR**, **INVESTIGAR
MÁS** o **DESCARTAR**.

Un falso CONSTRUIR es el peor error posible del sistema. Ante la duda, gana
INVESTIGAR MÁS. El LLM **etiqueta** la evidencia; el código **decide**.

## Mapa de capacidades

| Módulo | Responsabilidad | Depende de |
|---|---|---|
| `llm-provider` | Interfaz `LLMProvider` y su implementación Gemini: modelos en vivo, texto, streaming, JSON validado, contabilidad de costo | — |
| `evidence-store` | `EvidenceItem`, migración 009, upsert idempotente, `author_hash` con sal local, LanceDB con `source` e id global | — |
| `sources-core` | Contrato de adaptador, errores tipados, presupuestos, registro y estados de fuentes, perfil de escaneo, escaneo paralelo, deduplicación, modo comercial | `evidence-store` |
| `source-<id>` | Diez adaptadores oficiales, uno por fuente | `sources-core` |
| `niche-judge` | Filtro de calidad, etiquetado LLM con `evidence_span`, clustering multilingüe, siete dimensiones, ocho compuertas, abogado del diablo, Top 6 | `llm-provider`, `evidence-store`, `sources-core` |
| `ui-multifuente` | Fuentes en Configuración, resumen en la barra lateral, progreso por fuente, mapa de corroboración, panel del juez | todos |

Orden de construcción: `llm-provider` → `evidence-store` → `sources-core` →
`source-hackernews` → `source-stackexchange` → `source-github` →
`source-reddit` → `source-bluesky` → `source-youtube` → `source-mastodon` →
`source-discourse` → `source-producthunt` → `source-x` → `niche-judge` →
cierre. La UI de cada pieza va en el mismo commit que la pieza.

## Decisiones fijadas por el usuario (2026-09-23)

- **D-M1 · Persistencia.** Se crean tablas nuevas: `evidence_items`,
  `evidence_labels` (caché por hash de contenido), `evidence_duplicates`,
  `sources_state`, `cluster_evidence` y `niche_verdicts`.
  - `opportunity_clusters` se conserva (identidad D-G y validación).
  - `analyzed_signals`, `raw_posts` y `raw_comments` se congelan: se
    conservan, pero no reciben escrituras nuevas.
  - La migración copia `raw_posts` y `raw_comments` a `evidence_items` con
    el autor ya hasheado, y sustituye por su hash los autores en claro de las
    tablas antiguas (R9; hoy solo hay datos de demostración).
  - Las vistas de la UI se reescriben sobre `evidence_items`.
- **D-M2 · Embeddings.** `intfloat/multilingual-e5-large` (fastembed 0.8.0):
  1024 dimensiones, unos 100 idiomas, 2,24 GB. Usa los prefijos `query: ` y
  `passage: ` que exige e5. Cambiar de modelo obliga a recalcular los vectores
  de LanceDB (tabla nueva con el esquema de 1024 dimensiones).
- **D-M3 · Juez v1.**
  - Puntaje: `base = 0.25·frecuencia + 0.25·pago + 0.20·parches +
    0.15·hueco + 0.15·tendencia`, cada dimensión normalizada entre 0 y 1 con
    saturación con nombre (frecuencia 30 ítems, pago 5, parches 5, tendencia
    +100 % por ventana).
  - `convergencia = min(1, fuentes/3)` y `puntaje = 100 · base ·
    (0.5 + 0.5·convergencia)`. La viabilidad queda `undetermined`.
  - Tabla de veredictos, evaluada en orden:
    1. Falla G7 → DESCARTAR.
    2. G2 < N/2 autores → DESCARTAR.
    3. Fallan G1 y G2 a la vez → DESCARTAR.
    4. Falla G8 → como máximo INVESTIGAR MÁS.
    5. Fallan G1, G2 (con al menos N/2 autores) o G5 → INVESTIGAR MÁS.
    6. Fallan G3, G4 o G6 → INVESTIGAR MÁS, diciendo qué falta.
    7. Pasan todas → CONSTRUIR.
  - El abogado del diablo solo puede bajar el veredicto.
- **D-M4 · Presupuestos por defecto por escaneo.**
  - LLM: 300 ítems etiquetados y 1.000.000 de tokens.
  - Por fuente: 25 peticiones y 500 ítems.
  - YouTube: 2.000 unidades.
  - X: deshabilitada; necesita un tope en USD por escaneo y por mes.

## Stack

- Python 3.12, FastAPI (sidecar), LangGraph, PostgreSQL 18, LanceDB.
- google-genai 2.19.0 (ya instalado: `models.list`, `response_json_schema` y
  `usage_metadata.thoughts_token_count`).
- fastembed 0.8.0 y httpx 0.28.1.
- Tauri 2, Rust y React 19 con TypeScript.
- Sin dependencias nuevas mientras no se justifiquen (R10).

## Comandos

```
Python:  python -m unittest discover -s tests
Rust:    (cd ui/src-tauri && cargo test)
TS:      (cd ui && npx --no-install tsc --noEmit -p .)
Lint:    ruff check --no-cache ; mypy ; (cd ui/src-tauri && cargo clippy --all-targets -- -D warnings)
Migrar:  python scripts/migrate.py up            (base real: solo en el cierre, con respaldo previo)
Release: (cd ui && npm run tauri build)
```

## Estructura nueva

```
core/llm/            base.py (LLMProvider, errores, UsageRecord), gemini.py, budget.py
core/evidence/       model.py (EvidenceItem, SearchQuery), author.py (hash salado), store.py
core/sources/        base.py (contrato), errors.py, budget.py, registry.py, profile.py,
                     phrases.py (biblioteca versionada), scan.py (paralelo), dedup.py,
                     hackernews.py, stackexchange.py, github.py, reddit.py, bluesky.py,
                     youtube.py, mastodon.py, discourse.py, producthunt.py, x.py
core/judge/          quality.py, labeling.py, clustering.py, dimensions.py, gates.py,
                     verdict.py, devils_advocate.py, weights.py
sql/migrations/009_*.sql …
tests/fixtures/golden_pain_set.json   (≥ 60 ítems inventados, es/en)
```

## Contratos clave

- `EvidenceItem`: id global `<fuente>:<id_nativo>`, source, community, kind,
  title, text, url canónica, author_hash, created_at (UTC), fetched_at,
  language, thread_id, engagement normalizado (score, replies, reactions,
  views) más las métricas nativas en JSON, data_source (`real` o `demo`) y
  run_id.
- Errores comunes de fuente: `SourceCredentialsMissing`, `SourceAuthFailed`,
  `SourceForbidden`, `SourceNotFound`, `SourceRateLimited(retry_after)`,
  `SourceUnavailable` y `SourceBudgetExhausted`. Nunca un «0 resultados»
  silencioso.
- Estados de fuente: `no_configurada`, `configurada_sin_verificar`,
  `verificada` (con la hora del último acceso real), `error` (con código) y
  `deshabilitada_por_usuario`. Una fuente solo aparece en verde tras una
  respuesta real de la API.
- `LLMProvider`: `list_models()`, `generate_text()`, `stream_text()`,
  `generate_json(schema)`. Ningún módulo fuera del proveedor importa el SDK.

## Estrategia de pruebas

- TDD en cada unidad: el test falla primero, con salida visible. En la UI,
  el RED y el GREEN los da tsc.
- Los adaptadores se prueban con dobles fieles a la documentación oficial:
  códigos, paginación, cuotas y cuerpos de error, a través de
  `httpx.MockTransport`.
- La red real sigue R7: como máximo 20 peticiones por fuente pública en toda
  la misión, ninguna a X ni a Reddit, y como máximo 10 llamadas a Gemini, cada
  una registrada.
- Juez: un conjunto dorado de al menos 60 ítems inventados (es/en), tests de
  precisión con dobles del LLM, clusters hechos a mano (uno CONSTRUIR, uno
  INVESTIGAR MÁS por cada compuerta que puede fallar y uno DESCARTAR) y un
  test de honestidad (con 100 % demo no sale nunca CONSTRUIR).

## Límites

- **Siempre:** API oficial documentada, User-Agent identificable, atribución
  con enlace al original, respeto de Retry-After y de las cabeceras de cuota,
  hash salado del autor, tests primero, un commit atómico por unidad.
- **Preguntar antes:** cualquier decisión no fijada aquí, dependencias nuevas
  y cambios de esquema fuera de D-M1.
- **Nunca:** scraping, endpoints no documentados, cookies de sesión,
  suplantación de navegador, eludir límites, datos reales de usuarios en
  fixtures, nombres de usuario en claro, secretos impresos, llamadas reales a
  X o a Reddit.

## Fuentes que no se implementan

App Store, Google Play, G2, Capterra, Trustpilot, Quora e Indie Hackers: no
tienen API oficial para terceros. Google Trends: su API está en alfa cerrada;
no se implementa hasta tener acceso.

## Criterios de éxito

1. El motor de IA está detrás de `LLMProvider`, elige el modelo en vivo con
   `models.list` (familia 3.x) y lo verifican 2 llamadas reales.
2. Hay 10 adaptadores con el contrato común, cada uno con su tarjeta en
   Configuración y su botón Probar. Las fuentes públicas se verifican contra
   la API real; las demás quedan NO VERIFICADO y se dice por qué.
3. El juez es determinista, con 8 compuertas y cada una guardada con valor,
   umbral e ids de evidencia. El abogado del diablo solo baja. Hay test de
   honestidad y calibración con dobles y con concordancia real.
4. Tres suites en verde; ruff, mypy, clippy y tsc a 0.
5. Instalación limpia verificada, base real respaldada y migrada, un escaneo
   real de extremo a extremo con HN, Stack Exchange y Discourse, la release
   recompilada y `main` publicada por fast-forward.
