# Arquitectura: PostgreSQL y Frontend de Escritorio

> Fase 6 del Reddit Intelligence Radar.
> Estado: el **modelo de datos está implementado y verificado** contra
> PostgreSQL 18.6 (215 pruebas en verde, 39 de ellas del adaptador).
> El **frontend es especificación**: define contratos y estructura, no hay
> código de UI escrito todavía.

---

## 1. Por qué dos almacenes

El radar tiene dos preguntas que responder y no se parecen en nada:

| Pregunta | Almacén | Por qué |
|---|---|---|
| *"¿Qué se parece a «no puedo exportar facturas»?"* | **LanceDB** | Vecindad en un espacio de 384 dimensiones. Columnar, embebido, sin daemon. |
| *"¿Por qué el escaneo de anoche no encontró nada?"* | **PostgreSQL** | Integridad referencial, transacciones, agregados, auditoría. |

Mantener ambos **no es duplicación**: son índices distintos sobre el mismo
hecho. El puente es una sola columna, `analyzed_signals.embedding_ref`, que
guarda el identificador del registro en LanceDB.

`pgvector` **no está disponible** en la instalación de destino, lo cual
refuerza la decisión. Aun estándolo, mover los embeddings a PostgreSQL
obligaría a mantener dos fuentes de verdad sincronizadas para el mismo
vector, y a reindexar 384 dimensiones en cada escritura.

```
                    ┌──────────────────────────────┐
   Reddit  ──────►  │  core.ingestion  (Fase 2)    │
                    └──────────────┬───────────────┘
                                   ▼
                    ┌──────────────────────────────┐
                    │  core.intelligence (Fase 3)  │
                    └──────────────┬───────────────┘
                                   ▼
                    ┌──────────────────────────────┐
                    │  core.orchestration (Fase 5) │  grafo LangGraph
                    └───────┬──────────────┬───────┘
                            ▼              ▼
              ┌───────────────────┐   ┌──────────────────────┐
              │  LanceDB          │   │  PostgreSQL          │
              │  vectores + BM25  │◄─►│  rastro relacional   │
              │  búsqueda híbrida │   │  auditoría + feed    │
              └───────────────────┘   └──────────────────────┘
                     embedding_ref  ───┘
```

---

## 2. Modelo de datos

### 2.1 Tablas

| Tabla | Papel | Mutabilidad |
|---|---|---|
| `tenants` | Aislamiento multi-inquilino | Estable |
| `subreddits` | Qué se vigila, con qué frecuencia y con qué corte | Editable |
| `pipeline_runs` | Telemetría de cada ejecución del grafo | Append + cierre |
| `raw_posts` | Contenido crudo capturado | **Inmutable** |
| `raw_comments` | Comentarios crudos | **Inmutable** |
| `analyzed_signals` | Veredicto del motor: NLI, riesgos, scoring | Append |
| `jtbd_opportunities` | Síntesis accionable | **Editable por humanos** |

### 2.2 Cinco decisiones que conviene entender

**1. El contenido crudo es inmutable y se versiona por `content_hash`.**
La clave única es `(tenant_id, reddit_id, content_hash)`. Si alguien edita
su post, entra una fila nueva; la anterior se conserva. Motivo: el análisis
que se hizo sobre un texto debe seguir siendo explicable aunque ese texto ya
no exista. Verificado: insertar el mismo post dos veces no lo duplica;
cambiar el cuerpo sí crea una segunda versión.

**2. Una señal se analiza muchas veces y todas cuentan.**
`analyzed_signals` es única por `(tenant_id, run_id, reddit_id)`, no por
post. El mismo post analizado hoy y dentro de un mes da puntuaciones
distintas porque el factor de recencia decae. Guardar ambas permite ver
**cómo envejece** una oportunidad, que es justo la señal que interesa.

**3. `classifier_engine` registra quién clasificó.**
Hoy el NLI zero-shot corre en modo heurístico (deuda D1: `transformers` y
`torch` no están instalados). Cuando se habiliten, hará falta distinguir
qué filas vinieron de reglas y cuáles del modelo; sin esta columna, las
cosechas de antes y después serían incomparables.

**4. `pipeline_runs` desnormaliza `subreddit_name`.**
La FK es `ON DELETE SET NULL`: dejar de vigilar un subreddit no debe borrar
la evidencia de lo que se hizo. Pero un historial que dice `subreddit_id =
NULL` es inútil, así que el nombre se guarda aparte.

**5. Multi-tenant desde el primer día, RLS apagada.**
Añadir `tenant_id` después obliga a reescribir todos los índices y todas
las consultas. Llevarlo desde el principio no estorba en escritorio, donde
basta el tenant `…0001`. Las políticas RLS están **definidas pero no
activadas**: en local solo añadirían coste por fila.

### 2.3 Índices

54 índices. Los que responden a una consulta concreta del producto:

```sql
-- El dashboard al abrirse: lo cualificado y limpio, por puntuación.
CREATE INDEX analyzed_signals_qualified_idx
    ON analyzed_signals (tenant_id, final_score DESC)
    WHERE qualified AND cardinality(risk_flags) = 0;

-- El planificador: "¿qué toca escanear ahora?"
CREATE INDEX subreddits_due_idx
    ON subreddits (next_scan_at ASC NULLS FIRST)
    WHERE status = 'active';

-- La bandeja de trabajo: lo que nadie ha mirado aún.
CREATE INDEX jtbd_pending_idx
    ON jtbd_opportunities (tenant_id, created_at DESC)
    WHERE status IN ('new', 'triaged');
```

`EXPLAIN` confirma que el primero se usa: `Index Scan using
analyzed_signals_qualified_idx`.

**Full-text**: columnas `tsvector` **generadas**, no mantenidas por trigger,
de modo que no pueden desincronizarse del contenido. `raw_posts` y
`analyzed_signals` usan la configuración `english` (el contenido de Reddit
lo es); `jtbd_opportunities` usa `simple`, porque el *job statement* se
genera en español y un stemmer inglés lo destrozaría.

**Trigram** (`pg_trgm`) sobre `raw_posts.title`: la búsqueda semántica falla
con nombres propios de herramientas (`pgpool`, `Stripe VAT`). Verificado:
`'Saas' % 'SaaS'` → similitud 1.0.

### 2.4 Integridad verificada

Los siete casos que el esquema rechaza, comprobados uno a uno contra el
servidor real:

| Caso | Resultado |
|---|---|
| Señal sin origen (ni post ni comentario) | `CheckViolation` |
| Señal con doble origen (post **y** comentario) | `CheckViolation` |
| `final_score` = 150 | `CheckViolation` |
| Subreddit llamado `r/con barra` | `CheckViolation` |
| Post duplicado exacto | `UniqueViolation` |
| `urgency_tier = 'URGENTISIMO'` | `InvalidTextRepresentation` |
| Oportunidad `validated` sin fecha de validación | `CheckViolation` |

Cascadas: borrar un post arrastra sus señales y las síntesis JTBD
(`CASCADE` en cadena); borrar un subreddit **conserva** su historial de
ejecuciones (`SET NULL`).

---

## 3. Adaptador Python

`core/storage/postgres_store.py`. Separa deliberadamente dos cosas:

**Funciones puras** (verificables sin base de datos):
`normalize_buying_intent`, `normalize_pain_severity`, `normalize_sentiment`,
`normalize_willingness_to_pay`, `normalize_urgency_level`,
`compute_content_hash`, `to_timestamptz`, `post_to_row`, `signal_to_row`,
`opportunity_to_row`.

El clasificador produce etiquetas legibles (`"ready to buy"`); el esquema
usa slugs (`ready_to_buy`). Esa traducción vive en un único sitio, y un test
comprueba que **todo slug producido existe en `schema.sql`**: si alguien
añade una etiqueta al motor sin tocar el ENUM, la suite lo detecta.

**Repositorio asíncrono** `PostgresStore`:

```python
async with PostgresStore() as store:
    resumen = await store.persist_state(estado_final_del_grafo)
    # {'run_id': ..., 'posts': 12, 'signals': 12, 'opportunities': 12}
```

`persist_state()` es el puente con la Fase 5: toma el `RadarState` final y
escribe subreddit → ejecución → posts → señales → oportunidades **en una
sola transacción**. Si algo falla, hace rollback y marca la ejecución como
`failed`; no queda media cosecha escrita.

> **Windows**: psycopg async no funciona sobre `ProactorEventLoop`, que es
> el bucle por defecto. El módulo expone `run_async()`, que usa un
> `SelectorEventLoop`. No se cambia la política global de asyncio al
> importar, porque afectaría a todo el proceso sin avisar.

---

## 4. Puesta en marcha

```bash
# 1. Crear la base de datos
psql -h localhost -U postgres -c "CREATE DATABASE reddit_intelligence_radar"

# 2. Aplicar el esquema
psql -h localhost -U postgres -d reddit_intelligence_radar -f sql/schema.sql

# 3. Comprobar
psql -h localhost -U postgres -d reddit_intelligence_radar \
     -c "\dt radar.*" -c "SELECT slug FROM radar.tenants"
```

Sin `psql` en el PATH (caso de esta máquina, PostgreSQL 18 instalado sin
cliente de línea de comandos):

```bash
python -c "
import psycopg, pathlib
with psycopg.connect('host=localhost user=postgres dbname=postgres', autocommit=True) as c:
    c.execute('CREATE DATABASE reddit_intelligence_radar')
with psycopg.connect('host=localhost user=postgres dbname=reddit_intelligence_radar') as c:
    c.execute(pathlib.Path('sql/schema.sql').read_text(encoding='utf-8')); c.commit()
print('esquema aplicado')
"
```

Configuración (`.env`):

```
RIR_PG_DSN=host=localhost port=5432 user=postgres dbname=reddit_intelligence_radar
RIR_LANCEDB_PATH=F:\reddit_intelligence_radar\data\lancedb
```

**Migraciones**: el esquema aún no tiene versionado. Antes del primer
despliegue conviene decidirlo. Recomendación: archivos SQL numerados
(`sql/migrations/001_*.sql`) y una tabla `schema_migrations`, sin ORM —
el proyecto no usa SQLAlchemy y añadirlo solo para migrar sería desmedido.

---

## 5. Frontend: Tauri v2 + React 19 + Tailwind v4

### 5.1 Reparto entre procesos

Tres procesos, con una regla clara sobre quién habla con qué:

```
┌────────────────────────────────────────────────────┐
│  WebView   React 19 + Tailwind v4                  │
│            invoke() ▼          ▲ eventos           │
├────────────────────────────────────────────────────┤
│  Rust      comandos Tauri                          │
│            ├── LECTURAS  ──► PostgreSQL (sqlx)     │
│            └── MOTOR     ──► sidecar Python        │
├────────────────────────────────────────────────────┤
│  Python    FastAPI local: grafo, LanceDB, MCP      │
└────────────────────────────────────────────────────┘
```

**Rust lee PostgreSQL directamente con `sqlx`.** Abrir el dashboard no debe
cruzar dos procesos y un serializador para hacer un `SELECT`. `sqlx` además
verifica las consultas contra el esquema **en tiempo de compilación**: un
cambio en una columna rompe el build, no la aplicación en ejecución.

**El sidecar Python hace lo que solo él sabe hacer**: ejecutar el grafo,
generar embeddings y resolver la búsqueda híbrida sobre LanceDB. Es el mismo
patrón de sidecar que ya usa D&S Factory.

### 5.2 Estructura

```
frontend/
├── src-tauri/
│   ├── src/
│   │   ├── main.rs
│   │   ├── commands/
│   │   │   ├── radar.rs        # feed, detalle de oportunidad
│   │   │   ├── search.rs       # proxy al sidecar (híbrida)
│   │   │   ├── pipeline.rs     # disparar escaneos, telemetría
│   │   │   └── subreddits.rs   # CRUD de configuración
│   │   ├── db.rs               # pool sqlx
│   │   └── sidecar.rs          # ciclo de vida del proceso Python
│   └── tauri.conf.json
└── src/
    ├── views/
    │   ├── RadarView/          # dashboard principal
    │   ├── OpportunityDetail/  # deep-dive JTBD
    │   ├── SearchConsole/      # búsqueda híbrida
    │   └── PipelineControl/    # centro de control
    ├── components/
    │   ├── UrgencyBadge.tsx
    │   ├── ScoreBreakdown.tsx  # los 5 factores del scoring
    │   ├── EvidenceQuote.tsx
    │   └── RunTimeline.tsx
    ├── lib/
    │   ├── ipc.ts              # envoltorio tipado de invoke()
    │   ├── types.ts            # contratos (§5.4)
    │   └── queries.ts          # hooks de TanStack Query
    └── stores/
        └── uiStore.ts          # Zustand: filtros, selección, tema
```

### 5.3 Las cuatro vistas

**Radar View.** Tres zonas: subreddits vigilados con su salud (de
`v_subreddit_health`), feed de señales ordenado por urgencia (de
`v_radar_feed`) y una franja de métricas de la última ejecución. Las tarjetas
`CRITICAL` y `HIGH` se distinguen por forma además de por color, no solo por
rojo/naranja: el color por sí solo excluye a quien no lo percibe.

**Opportunity Deep-Dive.** La ficha JTBD completa, el desglose matemático de
la puntuación —los cinco factores como barras, no como un número suelto,
porque un 45 sin contexto no dice nada—, las citas literales del dolor con
enlace al hilo original, los competidores mencionados y los controles de
validación (`new → triaged → validated / rejected → shipped`).

**Consola de Búsqueda Híbrida.** Entrada única, resultados que muestran el
desglose RRF: rango denso, rango BM25 y puntuación fusionada. Que se vea
**por qué** apareció cada resultado es lo que distingue una consola de
investigación de una caja negra.

**Centro de Control del Pipeline.** Disparador manual, programación por
subreddit, telemetría de ejecuciones (`pipeline_runs`) y visor de errores no
fatales. Progreso en vivo por eventos Tauri, no por *polling*.

### 5.4 Contratos TypeScript

Sincronizados con los modelos Pydantic y los ENUM de PostgreSQL:

```typescript
// Espejo exacto de los ENUM del esquema.
export type UrgencyTier = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';

export type BuyingIntent =
  | 'ready_to_buy' | 'seeking_recommendation' | 'seeking_alternative'
  | 'comparing_products' | 'casual_discussion' | 'none';

export type PainSeverity =
  | 'severe_blocker' | 'time_consuming_friction'
  | 'minor_inconvenience' | 'no_problem' | 'none';

export type ValidationStatus =
  | 'new' | 'triaged' | 'validated' | 'rejected' | 'shipped';

export type RunStatus = 'running' | 'completed' | 'failed' | 'cancelled';

/** Fila de v_radar_feed. */
export interface RadarFeedEntry {
  signalId: string;
  redditId: string;
  subredditName: string;
  author: string;
  content: string;
  createdUtc: string;           // ISO 8601
  finalScore: number;           // 0-100
  urgencyTier: UrgencyTier;
  buyingIntent: BuyingIntent;
  painSeverity: PainSeverity;
  riskFlags: string[];
  qualified: boolean;
  opportunityId: string | null;
  jobStatement: string | null;
  currentSolution: string | null;
  competitorsMentioned: string[];
  workaroundDetected: boolean;
  validationStatus: ValidationStatus | null;
  postTitle: string | null;
  postPermalink: string | null;
  postScore: number | null;
  numComments: number | null;
}

/** Los cinco factores, cada uno en 0..1. */
export interface ScoreBreakdown {
  spreadFactor: number;
  frequencyFactor: number;
  severityFactor: number;
  recencyFactor: number;
  paidSignalFactor: number;
  rawScore: number;
  finalScore: number;
  urgencyTier: UrgencyTier;
}

/** Resultado de la búsqueda híbrida, con su desglose RRF. */
export interface HybridSearchHit {
  id: string;
  text: string;
  subreddit: string;
  opportunityScore: number;
  urgencyTier: UrgencyTier;
  jobStatement: string;
  rrfScore: number;
  denseRank: number | null;     // null = no lo encontró la rama densa
  bm25Rank: number | null;      // null = no lo encontró la rama léxica
  bm25Score: number | null;
}

/** Fila de v_subreddit_health: configuración + resultado del último escaneo. */
export interface SubredditHealth {
  subredditId: string;
  name: string;
  status: 'active' | 'paused' | 'error' | 'archived';
  lastScannedAt: string | null;
  nextScanAt: string | null;
  consecutiveFailures: number;
  lastRunId: string | null;
  lastRunStatus: RunStatus | null;
  lastRunStartedAt: string | null;
  lastRunDurationMs: number | null;
  fetched: number | null;
  qualified: number | null;
  errorCount: number | null;
}

/** Fila de pipeline_runs. */
export interface PipelineRun {
  id: string;
  subredditName: string;
  status: RunStatus;
  triggerSource: 'manual' | 'schedule' | 'mcp' | 'api';
  startedAt: string;
  finishedAt: string | null;
  durationMs: number | null;
  cycles: number;
  fetched: number;
  filteredIn: number;
  filteredOut: number;
  analyzed: number;
  stored: number;
  qualified: number;
  rejected: number;
  errors: string[];
  errorCount: number;
}
```

### 5.5 Comandos IPC

| Comando | Argumentos | Devuelve | Destino |
|---|---|---|---|
| `get_radar_feed` | `{ limit, minScore, urgencyTiers?, subreddit? }` | `RadarFeedEntry[]` | PostgreSQL |
| `get_opportunity_detail` | `{ redditId }` | `RadarFeedEntry & { breakdown: ScoreBreakdown }` | PostgreSQL |
| `update_opportunity_status` | `{ opportunityId, status, notes? }` | `void` | PostgreSQL |
| `list_subreddits` | `{}` | `SubredditHealth[]` | PostgreSQL |
| `upsert_subreddit` | `{ name, listing, limitPerPage, minScore, intervalMinutes }` | `string` | PostgreSQL |
| `list_runs` | `{ subredditId?, limit }` | `PipelineRun[]` | PostgreSQL |
| `search_hybrid` | `{ query, minScore, limit }` | `HybridSearchHit[]` | sidecar |
| `trigger_scan` | `{ subreddit, limit, sort }` | `string` (runId) | sidecar |
| `cancel_scan` | `{ runId }` | `void` | sidecar |

Envoltorio tipado, para que ningún componente llame a `invoke` con cadenas
sueltas:

```typescript
// lib/ipc.ts
import { invoke } from '@tauri-apps/api/core';

export const ipc = {
  getRadarFeed: (p: FeedParams) =>
    invoke<RadarFeedEntry[]>('get_radar_feed', p),
  triggerScan: (p: ScanParams) =>
    invoke<string>('trigger_scan', p),
  searchHybrid: (p: SearchParams) =>
    invoke<HybridSearchHit[]>('search_hybrid', p),
} as const;
```

**Eventos** (Rust → WebView), para el progreso en vivo:

```typescript
type RadarEvent =
  | { type: 'run:started';   runId: string; subreddit: string }
  | { type: 'run:progress';  runId: string; cycle: number; stats: RunStats }
  | { type: 'run:finished';  runId: string; qualified: number }
  | { type: 'run:error';     runId: string; message: string };
```

### 5.6 Estado

Dos tipos de estado que no deben mezclarse:

- **Estado del servidor** (feed, oportunidades, ejecuciones): **TanStack
  Query**. Es caché con invalidación, no estado propiamente dicho. Al
  recibir `run:finished`, se invalida la clave del feed y se refresca solo.
- **Estado de interfaz** (filtros activos, selección, tema, panel abierto):
  **Zustand**. Pequeño y sin ceremonia.

No hace falta Redux. El estado compartido real de esta aplicación es
pequeño; lo demás es caché de consultas.

**React 19**: `useOptimistic` para los cambios de estado de validación (el
cambio se pinta antes de confirmarse), Actions para los formularios de
configuración, y `use()` con Suspense para las cargas iniciales.

**Tailwind v4**: configuración en CSS con `@theme`, sin
`tailwind.config.js`. Los tokens de urgencia se definen una vez:

```css
@import "tailwindcss";

@theme {
  --color-urgency-critical: oklch(0.55 0.22 25);
  --color-urgency-high:     oklch(0.70 0.17 60);
  --color-urgency-medium:   oklch(0.80 0.12 95);
  --color-urgency-low:      oklch(0.65 0.03 250);
}
```

`oklch` porque mantiene la luminosidad percibida constante entre tonos:
`CRITICAL` y `HIGH` deben distinguirse por tono, no porque uno parezca más
apagado que el otro.

---

## 6. Pendiente antes de construir la UI

1. **Versionado del esquema.** Sin migraciones, el primer cambio en
   producción es manual y sin vuelta atrás.
2. **El corte de 60 puntos (deuda D6).** Una señal individual tiene un techo
   real de ~25-45 puntos, así que el dashboard mostrará la lista vacía por
   defecto. Antes de diseñar el Radar View hay que decidir: bajar el corte, o
   aplicar el gate sobre oportunidades **agregadas**, que es lo que el
   scoring presupone.
3. **El smoke real contra Reddit (deuda D8).** El esquema está verificado con
   datos sintéticos. Un payload real puede traer campos que no se previeron.
4. **NLI zero-shot (deuda D1).** Mientras siga en heurístico, las columnas
   `buying_intent` y `pain_severity` valen menos de lo que aparentan.
   `classifier_engine` deja constancia de ello en cada fila.
