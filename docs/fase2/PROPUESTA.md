# SENTRA · Fase 2 · Interfaz — propuesta

Estado: **propuesta, sin código de producto**. Rama `fase2/interfaz` (desde `main` 2688c3d).
La construcción espera la aprobación de Walter.

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

Estilo «sala de control»: denso, oscuro por defecto y con un solo acento.

- **Tokens únicos** (`maquetas/maqueta.css`) para toda la app, en claro y en oscuro con los mismos nombres:
  - superficies en 3 niveles, borde y borde fuerte;
  - tinta en 3 niveles;
  - acento cian;
  - estados ok, aviso, mal e info, cada uno con su versión suave.
- **Densidad:** controles de 34 px y filas de 40 px. La barra lateral mide 220 px y el contenido tiene un máximo de 1 080 px.
- **Una acción primaria por pantalla**, siempre en cian y con el coste escrito si gasta Gemini.
- **Colores de veredicto fijos en toda la app:** CONSTRUIR en verde, INVESTIGAR MÁS en ámbar y DESCARTAR en gris.
- **Tipografía del sistema** (Segoe UI Variable): sin dependencias nuevas ni fuentes descargadas.
- **Iconos:** se mantiene lucide-react, que ya es una dependencia. En las maquetas aparecen como cuadrados de sitio.

## 5. Decisiones abiertas (las toma Walter)

- **D1 · De dónde salen las palabras clave propuestas.**
  - **A. Gemini flash, 1 llamada por propuesta.** El coste medido en la maqueta es ilustrativo (≈ 1 300 tokens); el real se mide en el primer test contra el SDK falso.
    - Pasa por `ControlDeGemini`, con `purpose = palabras_clave`, y cuenta para los topes del día.
    - Da buenas palabras en los dos idiomas, sinónimos incluidos.
    - Cada «Proponer otra vez» gasta una llamada.
  - **B. Local, sin coste.** Plantillas de dolor por idioma («problema con X», «X is a pain»…) más frases parecidas de la evidencia ya guardada (e5).
    - No traduce: e5 no es un traductor. Las palabras en inglés las escribe la persona.
  - **C. Sin propuesta.** Solo chips manuales y el aviso de cobertura.
  - Recomiendo **A con B como respaldo**: si no hay clave o no queda presupuesto, se usa B y se dice.
- **D2 · Tema por defecto.** Oscuro, como en las maquetas, o seguir el sistema, como hoy.
- **D3 · Aviso al terminar si la persona cambió de pantalla durante el escaneo.** Hay dos opciones: notificación de Windows (el plugin de Tauri sería una dependencia nueva) o solo una insignia en «Nuevo escaneo» (sin dependencia). Recomiendo la insignia.

## 6. Commits previstos (TDD: el test se escribe y falla antes que el código)

Cada commit pasa por la compuerta completa (`CLIPPY=1 AUDIT=1 HUMO=1`) antes de hacerse.

| # | Commit | Tests (RED antes de GREEN) |
|---|---|---|
| 0 | `docs(fase2): propuesta, maquetas y capturas` (este) | — (solo documentación) |
| 1 | `fix(juez): el top sale de la última ejecución con nichos` | Base de prueba: ejecución A con INVESTIGAR MÁS y ejecución B posterior juzgada vacía. `/api/judge/top` devuelve los veredictos de A y `latestRun` = B. Con solo DESCARTAR, nada. Con `runId`, el comportamiento de hoy |
| 2 | `feat(documentos): estado guardado de dossier y plan por veredicto` | `GET /api/documents/status?verdictId=` responde guardado sí/no por tipo e idioma, leyendo solo el almacén. Test: 0 llamadas al SDK y 0 filas nuevas en el registro de uso |
| 3 | `feat(escaneo): proponer palabras clave` (según D1) | Con A: 1 fila en `llm_usage` con `purpose=palabras_clave`, 409 al superar un tope y respuesta validada con esquema. Con B: determinista y sin red (`prohibir_red_real`) |
| 4 | `feat(ui): cobertura de palabras clave` (`lib/cobertura.ts`) | `node --test`: 0, 2 solo ES, 6 en un idioma, 3+3, idioma elegido sin palabras y duplicados que no cuentan |
| 5 | `feat(ui): progreso por fuente en lenguaje llano` (`lib/progreso.ts`) | Un caso por fila de la tabla de la sección 3 y un código desconocido que no se oculta |
| 6 | `feat(ui): resultado con siguiente paso` (`lib/siguientePaso.ts`) | Con CONSTRUIR, solo INVESTIGAR, 0 nichos por autores, 0 piezas, tope de Gemini (`stop_reason`), cancelado y sin `judge_summary` (anterior a 019) |
| 7 | `feat(ui): tokens visuales únicos` (`styles.css`) | Test que exige que cada token del tema claro exista en el oscuro y viceversa; contraste AA de tinta sobre superficie y del acento |
| 8 | `feat(ui): asistente Nuevo escaneo (3 pasos)` | i18n: mismas claves en `es` y `en`. Humo: la pantalla inicial es «Nuevo escaneo»; recorrer los pasos 1-2 no crea filas en `llm_usage` (D1-A usa su SDK falso) |
| 9 | `feat(ui): escaneo en curso y resultado` | Humo con escaneo simulado (motor de prueba, sin fuentes reales): las filas por fuente y el resultado «0 nichos» con su siguiente paso |
| 10 | `feat(ui): Radar con último nicho válido y acceso a dossier/plan` | Humo: con la base de prueba del commit 1, el Radar muestra A y el aviso de B. «Dossier guardado» no llama a Gemini |
| 11 | `feat(ui): Fuentes compacta, Configuración en pestañas, Búsqueda con estado vacío` | Humo: las 5 vistas cargan sin excepciones; los botones de credenciales siguen enviando el valor una sola vez |
| 12 | `docs: CLAUDE.md y capturas de verificación de la Fase 2` | `tests/test_claude_md.py` con las rutas nuevas; capturas CDP del exe de cada pantalla, comparadas con las maquetas |

El humo navega hoy por las etiquetas «Radar en vivo», «Búsqueda semántica», «Fuentes» y «Configuración». Los commits 8 y 11 cambian esas etiquetas, así que actualizan el humo en el mismo commit.

## 7. Fuera de alcance

- La Fase 4 (modo Vídeos): Walter tiene su propio prompt.
- Cambios en las compuertas del juez o en sus umbrales.
- Escaneos reales o llamadas a Gemini durante la construcción, salvo lo que Walter apruebe. Los tests usan el SDK falso y bases `rir_*_test`.
