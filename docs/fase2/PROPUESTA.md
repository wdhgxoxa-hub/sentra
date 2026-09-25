# SENTRA · Fase 2 · Interfaz — propuesta

Estado: **aprobada por Walter el 25-09 (maquetas y decisiones D1-D3) y construida** (sección 9) en la rama `fase2/interfaz` (desde `main` 2688c3d).
Principios obligatorios en cada pantalla: P1 facilidad de uso y P2 preparada para el modo Videos (sección 6).

- Maquetas: `docs/fase2/maquetas/index.html`. Se abre con doble clic, sin servidor. Tiene conmutador claro/oscuro.
- Capturas del exe actual: `docs/fase2/capturas/`.

## 1. Cómo se tomaron las capturas

- Se capturó el exe instalado (`EXE_POR_DEFECTO` del humo) por CDP, a 1440×900.
- El perfil de WebView era aislado y la caché de modelos, fresca (`RIR_CACHE_MODELOS`). Así no hubo llamada a Google.
- El recorrido solo usó la barra lateral y el desplazamiento. No se pulsó ningún botón de acción.
- Resultado: 0 excepciones de JS y 0 filas nuevas en `llm_usage`.
- Hay 14 capturas (`<vista>_<n>.png`, de arriba abajo). La altura total de cada vista es:
  - Radar: 3 322 px;
  - Búsqueda: 900 px;
  - Fuentes: 4 075 px;
  - Configuración: 1 152 px.
- Los datos del diagnóstico salen de la base real, con consultas de solo lectura. Antes se comprobó que D&S Factory estaba libre (0 sesiones activas).

## 2. Diagnóstico

### Radar (`radar_1..5.png`)

1. **Pierde el último nicho válido.** Es un hecho comprobado.
   - El exe dice «El juez no formó ningún nicho en esta ejecución».
   - En la base, la última ejecución juzgada (24-09 18:47) tiene 0 veredictos.
   - La anterior (24-09 17:56) tiene 4: «Tener que reclamar facturas impagadas» (INVESTIGAR MÁS, 9 personas, puntuación 16,5) y 3 DESCARTAR.
   - Causa: `core/judge/store.py::latest_judged_run` elige la última ejecución *juzgada*, no la última *con nichos*.
2. **El mensaje vacío manda a otra pantalla.** Dice «Lanza un escaneo desde Fuentes», pero el formulario está al final de Fuentes, a más de 3 000 px de la parte de arriba.
3. **El 90 % de la pantalla es «Evidencia reciente» sin filtrar.** Por ejemplo: «Watching from Wendover Ontario», «Amen gloria a tir señor Jesús».
   - Cada pieza lleva la URL completa y la etiqueta «Datos reales».
   - Para una persona no técnica, eso parece el resultado del análisis, y no lo es.
4. **No hay acceso visible al dossier ni al plan.** Viven en el panel del juez, dentro de Fuentes.
5. **Faltan explicaciones.** Nada dice qué significa INVESTIGAR MÁS ni qué le falta a un nicho para ser CONSTRUIR.
   - El impagos cae por la regla 9: alguien menciona una alternativa que le funciona, pero son menos de 3 personas.

### Búsqueda (`busqueda_1..2.png`)

6. Es una caja de texto sobre una pantalla vacía. No dice cuánta evidencia hay para buscar (2 221 piezas), ni da ejemplos, ni aclara que no gasta Gemini.

### Fuentes (`fuentes_1..5.png`)

7. **Mezcla tres trabajos en 4 075 px:**
   - configurar 10 fuentes, cada una en una tarjeta con credenciales, términos y coste siempre abiertos;
   - lanzar un escaneo («Escanear por perfil»);
   - ver los veredictos del juez.
8. **El escaneo es un formulario técnico.** Pide «Nombre del perfil», «Ventana (días)», «Tema (palabras clave, separadas por comas)», «Modo descubrimiento» e «Idiomas en/es».
   - No propone palabras clave.
   - No avisa de la mala cobertura: con 2 palabras en un solo idioma, lo normal es 0 nichos.
9. **El progreso usa lenguaje interno.** Muestra «En curso · N ítems», «Falló · N ítems conservados» y códigos como `source_rate_limited` en un `ErrorNotice`.
10. **El final del escaneo son cifras sin siguiente paso.** Dice «N traídos · N únicos · N duplicados entre fuentes», «Guardado como run <uuid>».
    - Con 0 nichos, solo queda la frase del juez. No se dice qué hacer.

### Configuración (`configuracion_1..2.png`)

11. Funciona y es honesta, pero es una sola columna larga: apariencia, clave, modelos y presupuesto.
12. El consumo del día y las últimas llamadas no están a la vista junto a los topes.

### Transversal

13. Hay dos tamaños de título que compiten. Las tarjetas miden unos 770 px de ancho sobre una pantalla de 1 440 px, y el resto queda vacío.
14. La acción principal de la app, escanear, no está en la navegación.
15. El tema claro es el que viene por defecto. El oscuro existe, pero con otra paleta de tokens.

## 3. Rediseño

### Navegación

- **Nuevo escaneo** pasa a ser la primera entrada y la pantalla de inicio: botón «+», separado del resto.
- Después vienen Radar, Búsqueda, Fuentes y Configuración.
- El pie de la barra lateral muestra el estado real: fuentes listas, base y motor, y Gemini de hoy («2 de 40 llamadas»).

### Requisitos de Walter y dónde se resuelven

| Requisito | Solución | Maqueta |
|---|---|---|
| Pantalla principal «Nuevo escaneo», asistente de 3 pasos | Tema → Palabras clave → Presupuesto y escanear. El nombre del perfil sale del tema y se puede editar en el paso 3 | 01, 02, 03 |
| Palabras clave propuestas en ES y EN, editables | Dos filas de chips por idioma, con quitar, añadir y «Proponer otra vez». La fuente de las propuestas es la **decisión D1** | 02 |
| Aviso de cobertura | Función pura `coberturaDePalabras`. Avisa si hay menos de 6 palabras, un solo idioma o menos de 3 en algún idioma elegido. No bloquea: «Seguir igualmente» | 02 |
| Confirmación de presupuesto | Mismo contrato que la Fase 1 (`/api/scan/estimate` + confirmación obligatoria). El botón lleva el coste escrito («Escanear · ≈ 6 llamadas»). Sin presupuesto no hay botón y se dice por qué | 03 |
| Progreso por fuente entendible | 4 fases (Buscar, Limpiar, Juez, Resultado). Cada fuente tiene una línea con punto de color, una frase llana y un número | 04 |
| Resultado en lenguaje llano con siguiente paso, incluido «0 nichos» | Función pura `siguientePaso(resultado)`. Cubre: con CONSTRUIR, solo INVESTIGAR MÁS, 0 nichos por pocas personas, 0 piezas, cortado por tope de Gemini y cancelado | 05, 06 |
| El Radar no pierde el último nicho válido | Motor: el top sale de la última ejecución **con veredictos** no descartados. Si la última juzgada salió vacía, se añade un aviso con enlace a su resultado | 07 |
| Acceso visible a dossier y plan | Botones en cada nicho del Radar y ficha de nicho con estado («guardado · sin coste» o «sin generar») y coste escrito antes de pulsar | 07, 08 |
| Dirección visual coherente | Tokens únicos (sección 4) aplicados a todas las vistas | todas |

Maquetas de las vistas que no son nuevas, pero se reordenan: Fuentes (09), Configuración (10) y Búsqueda (11).

- **Fuentes (09):** una fila por fuente con estado, última respuesta e interruptor. «Detalles» abre las credenciales, el coste y los términos. El escaneo y el juez salen de aquí.
- **Configuración (10):** pestañas. Gemini y presupuesto van juntos, con el consumo del día y las últimas filas de `llm_usage`.
- **Búsqueda (11):** estado vacío que dice cuánto hay, de cuándo a cuándo y que no gasta. Incluye ejemplos que se pueden pulsar.

### Frases del progreso por fuente

Una función pura, con un test por fila.

| Estado / código | Frase | Color |
|---|---|---|
| running | «Buscando…» y el número traído hasta ahora | cian, pulsante |
| done | «Listo» | verde |
| cancelled | «Lo cancelaste; se guarda lo traído» | gris |
| source_rate_limited | «Nos pidió esperar; seguimos con lo que ya trajo» | ámbar |
| source_budget_exhausted | «Se acabó su cuota de hoy» | ámbar |
| source_credentials_missing | «Falta conectar la cuenta (Fuentes)» | rojo |
| source_auth_failed | «La clave no funciona; revísala en Fuentes» | rojo |
| source_forbidden / source_not_found | «La fuente rechazó la búsqueda» | rojo |
| source_unavailable / source_error / internal_error | «No respondió. Las demás siguen; puedes probarla luego en Fuentes» | rojo |
| source_pending_approval | «No se usa: pendiente de aprobación» | gris |
| apagada | «No se usa: apagada» | gris |

Un código desconocido nunca se oculta. Muestra «Error inesperado (código)».

### El Radar no pierde el último nicho: contrato

- `GET /api/judge/top` devuelve lo mismo que hoy, pero de la última ejecución que tenga al menos un veredicto CONSTRUIR o INVESTIGAR MÁS.
- Añade `latestRun: {runId, startedAt, verdicts, summary, stopReason}` con la última ejecución juzgada, aunque esté vacía.
- La UI muestra el aviso si `latestRun.runId` es distinto del run que se está mostrando.
- Con `runId` explícito, el comportamiento no cambia.
- Las ejecuciones anteriores a la migración 019 no tienen `judge_summary`. El texto lo dice («sin detalle para escaneos anteriores al 25-09») y no inventa cifras.

## 4. Dirección visual

Estilo «sala de control», con un solo acento. El tema sigue al de Windows (D2), y los dos temas están cuidados por igual.

- **Tokens únicos** (`maquetas/maqueta.css`) para toda la app, en claro y en oscuro con los mismos nombres:
  - superficies en 3 niveles, borde y borde fuerte;
  - tinta en 3 niveles;
  - acento cian;
  - estados ok, aviso, mal e info, cada uno con su versión suave.
- **Densidad legible (P1):** texto base de 15 px, botones de al menos 36 px y la acción principal de 44 px. La barra lateral mide 220 px y el contenido tiene un máximo de 1 080 px.
- **Una acción primaria por pantalla**, siempre en cian y con el coste escrito si gasta Gemini.
- **Colores de veredicto fijos en toda la app:** CONSTRUIR en verde, INVESTIGAR MÁS en ámbar y DESCARTAR en gris.
- **Tipografía del sistema** (Segoe UI Variable): sin dependencias nuevas ni fuentes descargadas.
- **Iconos:** se mantiene lucide-react, que ya es una dependencia. En las maquetas aparecen como cuadrados de sitio.

## 5. Decisiones de Walter (25-09)

- **D1 · Palabras clave: A, con B de respaldo.**
  - **A.** Gemini propone las palabras clave en una llamada.
    - La llamada queda registrada en `llm_usage` con `purpose = palabras_clave` y cuenta para los topes del día.
    - Hace falta la migración 020: el CHECK de `llm_usage.purpose` solo admite los propósitos de la 017.
  - **B.** Se usa si no hay clave, si no queda presupuesto o si Gemini falla. La pantalla lo dice.
    - Son plantillas de queja por idioma construidas con el tema que escribe la persona. No tienen coste ni usan la red.
    - B no traduce. Si la persona escribe el tema en español, las palabras en inglés las añade ella. El aviso de cobertura se lo pide.
    - Cambio respecto de la propuesta: dejé fuera las frases parecidas de la evidencia guardada (e5). Obligaban a cargar el modelo de 2,1 GB solo para proponer palabras, y traían ruido. Queda en el registro de decisiones.
  - **Aviso de cobertura:** sale cuando todas las palabras quedan en un solo idioma, además de los demás casos (menos de 6 palabras, o menos de 3 en algún idioma elegido).
- **D2 · Tema.** Sigue el de Windows. Configuración tiene un conmutador manual con tres opciones: Claro, Oscuro y Como Windows. El mecanismo ya existe (`data-theme` y `settingsStore`); cambian los tokens.
- **D3 · Aviso al terminar.** Una marca en «Nuevo escaneo» cuando el escaneo termina y la persona está en otra pantalla. Sin dependencias nuevas.

## 6. Principios obligatorios en cada pantalla

### P1 · Facilidad de uso ante todo

Cualquier persona, de un niño a alguien de cien años, entiende cada pantalla sin ayuda.

| Regla | Cómo se cumple | Cómo se vigila |
|---|---|---|
| Frases cortas y palabras de todos los días; nada de jerga | Los textos visibles están en `i18n/es.ts` y `en.ts`, fuera del bloque `detalle`. La jerga solo puede ir en `detalle`, que únicamente se pinta dentro de `<VerDetalle>` (un desplegable «Ver detalle» cerrado) | **Guardia 1** (`tests/test_lenguaje_llano.py`): ningún literal fuera de `detalle` contiene una palabra prohibida. **Guardia 2**: `t.detalle` solo se usa en `components/detalle/`. **Guardia 3** (humo): el texto visible de cada pantalla del exe real, con los desplegables cerrados, no contiene ninguna palabra prohibida |
| Palabras prohibidas en lo visible | `token(s)`, `G0`–`G9`, `cluster`, `pipeline`, `regla N` y `rule N`, `LLM`, `prompt`, `API`, `JSON`, `sidecar`, `uuid`, `embedding`, `e5`, `backoff`, `OAuth`, `endpoint`, `compuerta` y `gate`, `run`/`runId` | La lista vive en un solo sitio (`tests/_lenguaje_llano.py`), que usan las tres guardias |
| Tokens → lenguaje llano | «unidades de texto» (Gemini cobra por ellas). Las cifras son las mismas; cambia el nombre | Guardia 1 |
| Códigos → frases | Cada código de fuente o de parada tiene su frase (sección 3). Un código desconocido dice «Error inesperado» y deja el código en «Ver detalle» | Tests de `lib/progreso.ts` y `lib/siguientePaso.ts` |
| Nombres de credenciales | `api_key`, `bearer_token`, `client_id`… se muestran como «Clave», «Código de acceso», «Identificador de la app»… | Test del mapa: todo campo del catálogo de fuentes tiene nombre llano en los dos idiomas |
| Una sola acción principal, grande y evidente | El componente `AccionPrincipal`, de 44 px de alto y en color de acento, puede aparecer una sola vez por pantalla | El humo cuenta `[data-accion-principal]` = 1 en cada pantalla nueva |
| Cada resultado dice qué significa y qué hacer ahora | `siguientePaso()` devuelve siempre `{titulo, significa, pasos[≥1]}` | Test: ningún caso devuelve 0 pasos |
| Letra legible, buen contraste, botones grandes | Texto base de 15 px (hoy 14); nada por debajo de 13 px, salvo notas de 12 px. Botones de al menos 36 px. Contraste AA (4,5:1) de la tinta y de los estados sobre su superficie, en claro y en oscuro | Test de tokens: contraste calculado desde OKLCH; en los dos temas existen los mismos tokens |
| Nada depende solo del color | Cada estado lleva icono y palabra («Listo», «Falló», «No se usa») además del color. Cada veredicto lleva su nombre | Tests de `progreso.ts`: cada estado tiene `palabra` e `icono` |

### P2 · Pensar en el modo Videos (sin construirlo)

La interfaz queda preparada para enchufar Videos sin rehacer nada.

1. **Registro de modos** (`ui/src/modos/`):
   - `tipos.ts` define `Modo`: `id`, textos del asistente, del resultado y de la ficha, las métricas que se enseñan de un nicho y los documentos que tiene.
   - `software.ts` es el único modo registrado hoy.
   - `index.ts` exporta `MODOS` y `modoActivo`. El modo activo vive en `uiStore.modo` y hoy siempre vale `"software"`.
2. **Barra lateral:** tiene el hueco reservado `SelectorDeModo` (Software | Videos).
   - Se pinta solo si hay 2 o más modos registrados, así que hoy no se ve. No miente: no promete nada que no exista.
   - Test: con un modo, el selector no se pinta. Con dos modos de prueba, se pinta.
3. **Componentes genéricos:** `Asistente`, `Resultado`, `TarjetaDeNicho` y `FichaDeNicho` reciben un `NichoEnPantalla` y un `Modo`. No importan `JudgeVerdict`.
   - `NichoEnPantalla` = `{id, tipo, nombre, subnombre, veredicto, metricas: Metrica[], explicacion, documentos: DocumentoDelNicho[]}`. El `tipo` («software» / «videos») es un dato.
   - El adaptador `modos/software.ts::nichoDeSoftware(v)` convierte un veredicto del juez en `NichoEnPantalla`.
   - Test: los componentes genéricos se prueban con un nicho de tipo «videos» inventado y funcionan sin tocarlos.
4. **Compartido:** Fuentes y Configuración no dependen del modo.
5. **Cómo se enchufará Videos**, cuando Walter lo apruebe con su propio prompt:
   - Escribir `modos/videos.ts` con sus textos, métricas y adaptador `nichoDeVideos`.
   - Registrarlo en `MODOS`, con lo que aparece el selector.
   - Dar al motor sus rutas propias. El contrato lo define Walter.
   - Nada de lo construido en esta fase cambia.
   - Queda descrito también en CLAUDE.md, sección «Modo Videos: cómo se enchufa».

## 7. Commits de la construcción (TDD: el test se escribe y falla antes que el código)

Cada commit pasa por la compuerta completa (`CLIPPY=1 AUDIT=1 HUMO=1`) antes de hacerse. Cuando el commit toca la UI o el motor, el exe de release se recompila antes (`npm run tauri build`), porque el humo prueba el exe.

| # | Commit | Tests (RED antes de GREEN) |
|---|---|---|
| 0 | `docs(fase2): propuesta, maquetas y capturas` | hecho: b78be5e |
| 0b | `docs(fase2): principios P1 y P2 y decisiones D1-D3` (este) | — |
| 1 | `fix(juez): el Radar muestra la última ejecución con nichos` | Base de prueba: A con INVESTIGAR MÁS y B posterior vacía → los veredictos de A y `latestRun` = B. Solo DESCARTAR → nada. Con `runId`, igual que hoy. El humo cuenta con la regla nueva |
| 2 | `feat(documentos): saber si el dossier y el plan ya están guardados` | `GET /api/documents/status`: guardado sí/no por tipo e idioma, 0 llamadas al SDK. Exportar algo guardado no resuelve el modelo (0 llamadas, ni para listar modelos) |
| 3 | `feat(escaneo): proponer palabras clave (Gemini y respaldo local)` | Migración 020 (`palabras_clave` en el CHECK). A: 1 fila en `llm_usage`, 409 al superar el tope y esquema validado. B sin clave, sin presupuesto o con error: plantillas, sin red y 0 filas. Contrato Rust ↔ TS |
| 4 | `feat(ui): aviso de cobertura de palabras clave` | `node --test`: 0 palabras, 2 solo ES, todo en un idioma, 3+3, idioma elegido sin palabras y duplicados que no cuentan |
| 5 | `feat(ui): progreso por fuente en palabras de todos los días` | Un caso por código, cada estado con palabra e icono, y un código desconocido que no se oculta |
| 6 | `feat(ui): el resultado dice qué significa y qué hacer` | CONSTRUIR, solo INVESTIGAR MÁS, 0 nichos, 0 piezas, tope de Gemini, cancelado y sin resumen (anterior a la 019). Nunca 0 pasos |
| 7 | `feat(ui): tokens visuales, letra legible y guardia de lenguaje llano` | Contraste AA y paridad de tokens. Guardias 1 y 2 sobre los bloques nuevos de i18n |
| 8 | `feat(ui): modos y asistente «Nuevo escaneo» en 3 pasos` | Registro de modos, selector oculto con un modo y paridad de i18n. Humo: arranca en «Nuevo escaneo», 1 acción principal y guardia 3; los pasos 1-2 sin filas nuevas en `llm_usage` (solo se proponen palabras al pulsarlo) |
| 9 | `feat(ui): escaneo en curso, resultado y marca al terminar` | Reductor de la marca (D3). Humo: el resultado con el último escaneo guardado dice qué hacer |
| 10 | `feat(ui): Radar y ficha de nicho genéricos con dossier y plan a la vista` | Componentes con un nicho «videos» inventado. Humo: el Radar enseña el nicho de la última ejecución con nichos, su aviso y los botones de dossier y plan |
| 11 | `feat(ui): Fuentes, Configuración y Búsqueda en lenguaje llano` | Mapa de credenciales. La guardia 1 cubre ya todo i18n. Humo: 5 pantallas, guardia 3 en todas |
| 12 | `docs: CLAUDE.md, modo Videos y capturas de la Fase 2` | `tests/test_claude_md.py` con migración 020, `/api/documents/status`, `/api/scan/keywords` y «Modo Videos» |

## 8. Fuera de alcance

- La Fase 4 (modo Vídeos): Walter tiene su propio prompt.
- Cambios en las compuertas del juez o en sus umbrales.
- Escaneos reales o llamadas a Gemini durante la construcción, salvo lo que Walter apruebe. Los tests usan el SDK falso y bases `rir_*_test`.

## 9. Resultado de la construcción (25-09)

Todos los commits pasaron la compuerta completa (`CLIPPY=1 AUDIT=1 HUMO=1`) y el exe de release se recompiló antes de cada uno que tocaba la interfaz o el motor. Las capturas del exe real, en claro y en oscuro, están en `docs/fase2/capturas-exe/`, con `informe.json`: acciones principales y jerga por pantalla, 0 excepciones y 0 filas nuevas en `llm_usage`.

| # | Commit | Qué | RED → GREEN |
|---|---|---|---|
| 0 | b78be5e | Propuesta, maquetas y capturas | — |
| 0b | 53c7c36 | Principios P1 y P2, D1-D3 | — |
| 1 | f4b4cc2 | El Radar enseña la última ejecución con nichos y avisa | ImportError, contrato y humo 0≠2 → verde |
| 2 | 680d834 | Estado de documentos; reutilizar sin resolver el modelo | 405 y «no debe resolver el modelo» → verde |
| 3 | ab92058 | Palabras clave con Gemini y respaldo; migración 020 | CheckViolation, módulo ausente → verde |
| 4 | 1bcb32d | Aviso de cobertura | módulo ausente → 6/6 |
| 5 | 401cc94 | Progreso por fuente en palabras llanas | módulo ausente → 15/15 |
| 6 | 1b0a7d2 | Resultado: qué significa y qué hacer | módulo ausente → 10/10 |
| 7 | 4ca0273 | Acento cian, letra de 15 px, guardia de lenguaje llano | tono 265 y 4,30:1 → verde |
| 8 | 3f81717 | Modos y asistente de 3 pasos (con el escaneo en curso) | modos, humo del asistente → verde |
| 9 | b36e41a | Resultado genérico y marca D3 | resultado.test → 4/4 |
| 10 | ae94607 | Radar y ficha genéricos, dossier y plan a la vista | humo del Radar nuevo → verde |
| 11 | 2d4f031 | Fuentes, Configuración y Búsqueda llanas; guardia total | guardias ampliadas → verde |
| rev | c3ef59a | Revisión: textos sin uso retirados | — |
| 12 | (este) | CLAUDE.md, cómo se enchufa Videos, capturas finales y cifras de Búsqueda a «Ver detalle» | test_claude_md → verde |

Desvíos respecto del plan de la sección 7:

- El escaneo en curso entró en el commit 8, con el asistente: «Escanear» no puede existir sin su progreso. El resultado fue al 9.
- Rust e ipc de palabras clave fueron al commit 8, no al 3: el test de superficie exige que cada método de `ipc` lo use una vista.
- Se añadió un commit de revisión. En el 12, la tabla de Búsqueda deja de enseñar las columnas «Semántica / Exacta / Combinada» con sus cifras: pasan a «Ver detalle» de cada resultado.

Errores míos durante la construcción, corregidos en la raíz:

- **Espera vacía en el arnés.** Una espera sobre `document.querySelector(...)` sin `!!` nunca se cumplía, porque el nodo llega por CDP como `{}`. Me hizo creer que el asistente no pasaba al paso 2, y lo desmintió una sonda. La misma espera hacía que la búsqueda del humo esperase siempre 15 s. Ahora un test lo impide.
- **Enlace «Abrir» que no hacía nada.** Lo puse en la ficha, pero la ventana no abre enlaces externos. Se quitó, y una guardia impide volver a ponerlo.

No verificado:

- El escaneo en curso y el resultado justo después de un escaneo real: el humo no escanea y no había aprobación para escanear. El componente de resultado sí se ve en el exe desde el aviso del Radar («cero_nichos»).
- «Proponer palabras» con Gemini de verdad: probado con el SDK falso. En el exe no se pulsó, para no gastar.
- Los componentes genéricos pintados con un nicho de tipo «videos»: sin pruebas de componentes con DOM, que exigirían una dependencia nueva. Lo que sí se comprueba es la guardia estática y el adaptador con node.
- La marca D3 en el exe: exige terminar un escaneo real. La lógica tiene test.

Hallazgo fuera de alcance: el adaptador de Mastodon guarda como «URL del original» la de la API (`/api/v1/statuses/{id}`).
