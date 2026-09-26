# Fase 3 · Diagnóstico del escaneo 2: calidad de las quejas, agrupación y Bluesky

Escaneo del 25-09, ejecución `01a0dad3-844c-7e42-863d-a912d331064d`, «Perseguir a los clientes para que manden sus documentos al contable».

- **Palabras:** 14 (6 en español y 8 en inglés).
- **Traídas:** 483. Bluesky 250, GitHub 111, Mastodon 73, Stack Exchange 42, YouTube 7.
- **Juez:** 394 piezas, 301 etiquetadas y 53 con queja real. Salieron 4 grupos y los 4 se descartaron por G0 («no es un mismo problema»).

**Método.** Solo lectura de la base y de los vectores guardados (LanceDB `evidence_e5`). Todo se recalculó en local con el modelo e5 del motor. Sin Gemini y sin escanear. Scripts en el directorio temporal de la sesión: `sonda_quejas.py`, `sonda_53.py`, `medir_tema_*.py`, `medir_umbral.py` y `medir_bluesky.py`.

## Punto 3 · Las 53 quejas

**Fuente:** Stack Exchange 29, GitHub 21, Bluesky 2, YouTube 1. Hay 55 piezas con `is_pain=yes`; el juez aparta 2 como anuncios.

**Del tema: 0 de 53.** Una es tangencial: una lista de documentos por caso en un despacho legal (GitHub). El resto son fallos técnicos (JSON, Typesense, Firestore, formularios) o noticias personales. El etiquetado no se equivoca: son quejas de verdad, pero de otra cosa.

### Por qué pasaron

1. **El filtro de tema solo mira comentarios.**
   - `sin_comentarios_fuera_de_tema` descarta un comentario que no nombra el tema.
   - Los posts, las preguntas y los issues no pasan por ahí: se da por hecho que su búsqueda ya era del tema.
   - Hoy dejó fuera 0 piezas.
2. **Aunque mirara todo, no separaría.** `menciona_el_tema` acepta cualquier raíz de 6 letras de cualquier palabra. «docume», «client», «collec», «missin» y «pendie» salen en casi cualquier texto técnico. En el escaneo 2 pasan 331 de 393 piezas y 55 de 55 quejas.
3. **El etiquetador no conoce el tema.**
   - El prompt de `labels.py` no lo recibe, y la caché va por `content_hash`: una etiqueta vale para cualquier escaneo.
   - `is_pain` significa «hay un problema», no «hay un problema de este tema».
4. **Dos fuentes no casan con este tema.**
   - Stack Exchange busca siempre en `stackoverflow`, que es de programación.
   - GitHub solo tiene issues de software. Para un tema que no es de software, cualquier «documento» o «cliente» es de código.

### Filtros locales medidos (ninguno sirve)

| Filtro (título + texto) | Escaneo 1 (PDF a Word): pasan / quejas que pasan | Escaneo 2: pasan / quejas que pasan |
|---|---|---|
| Hoy: cualquier raíz | 35 de 462 / 5 de 5 | 331 de 393 / 55 de 55 |
| Todas las raíces de un término | 8 / 1 de 5 | 269 / 51 de 55 |
| Raíces de un término juntas (ventana de término + 3) | 1 / **0 de 5** (pierde la única buena) | 135 / 17 de 55, **todas fuera del tema** |
| Similitud e5 con el nombre o las palabras | Todo entre 0,72 y 0,85, sin corte | Todo entre 0,76 y 0,84; «Muchas gracias por el contenido» queda arriba |

Lo léxico y lo semántico local no distinguen «perseguir a clientes por sus documentos» de «la documentación del cliente de Redis». Esa distinción solo la hace un modelo que lea la pieza y sepa el tema.

### Propuestas (esperan decisión de Walter)

- **A. El etiquetador recibe el tema.**
  - Devuelve un campo más, «del tema» (sí/no, con su fragmento). Solo cuenta como queja `is_pain ∧ del_tema`.
  - Mismas llamadas a Gemini; el prompt crece con el tema (estimación, no medido).
  - Coste: la caché pasa a ir por (pieza, tema) y es labels-v5, así que no se reutilizan etiquetas entre temas.
  - Solo se puede verificar con un escaneo real.
- **B. Fuentes según el tipo de tema.**
  - Si el tema no es de software, GitHub no se consulta.
  - Stack Exchange elige un sitio afín (hoy siempre `stackoverflow`).
  - Pide decidir quién dice qué tipo es el tema: el asistente o Gemini al proponer palabras.
- **C. Mínimo sin gasto: el filtro actual para todas las piezas, no solo comentarios.** Medido: apenas filtra (331 de 393). No lo recomiendo solo.

Recomiendo **A + B**. Lo que se vio en el escaneo 2 es honesto por otro motivo: G0 descartó los 4 grupos. La red de seguridad funcionó, pero se gastó el cupo de etiquetado en ruido.

## Punto 4 · Agrupación con umbral 0,82

El arnés reproduce **exactamente** los 4 grupos guardados, con las mismas piezas. Medidas sobre las 53 frases de dolor del escaneo:

- **Entre pares de quejas sin relación:** similitud mediana 0,794 y p90 0,830. **264 de 1 378 pares (19 %) están en 0,82 o más.** Con frases cortas, e5 pone lo que no tiene relación entre 0,75 y 0,83: el umbral cae dentro de ese ruido.
- **Los grupos juntan registro e idioma, no problema:**
  - «json · look · results» (14 quejas): Typesense, Firebase, Power Pivot, gRPC… Media 0,830 y mínimo 0,773.
  - «button · fields · empty» (11): CLI de defradb, iframe, GTM, Prisma… Media 0,827.
  - «genera · mayor · operación» (4): cuatro issues de ERP en español sobre cosas distintas.
  - El grupo sin palabras (5): quejas en español sin nada en común.

Barrido del umbral:

| Umbral | Escaneo 2: grupos (tamaños) | Conjunto dorado: grupos · pureza · ARI |
|---|---|---|
| 0,80 | 2 (31, 10) | 3 · 0,241 · 0,044 |
| **0,82 (hoy)** | 4 (14, 11, 5, 4) | 10 · 0,556 · **0,268** |
| 0,84 | 7 (4, 4, 3, 3, 3, 3, 3) | 11 · 0,750 · 0,193 |
| 0,85 | 3 (4, 3, 3) | 11 · 0,824 · 0,183 |
| 0,86 | **0** | 9 · 0,870 · 0,164 |
| 0,88 | 0 | 4 · 0,954 · 0,033 |

Aviso: el comentario de `clustering.py` dice pureza 0,735 a 0,82, pero el barrido de hoy sobre el conjunto dorado da 0,556. El dato del código está desfasado; no he investigado desde cuándo.

### Propuestas (esperan decisión de Walter)

- **A. Subir a 0,85.**
  - Dorado: pureza de 0,556 a 0,824, ARI de 0,268 a 0,183.
  - Escaneo 2: 3 grupos pequeños que G0 seguiría descartando.
- **B. Subir a 0,86.**
  - Dorado: pureza 0,870 y ARI 0,164.
  - Escaneo 2: 0 grupos, que es lo correcto con este ruido.
  - En el dorado forma 9 grupos en vez de 10 (no he medido cuáles se pierden).
- **C. Dejar 0,82 y apoyarse en G0.** Hoy ya descarta las mezclas, con 1 llamada por escaneo, pero se enseñan grupos que no lo son.

Recomiendo decidir el punto 3 primero: con menos ruido de entrada, el umbral pesa menos. Si hay que elegir ya, **A (0,85)**.

## Punto 5 · Bluesky trajo 250 de 483

- **Duplicadas:** 83 de 250 (33 %). Etiquetadas 116, con queja real 2 (las dos fuera del tema, en el punto 3).
- **Muestra de 40 al azar (semilla 25):**
  - **0 quejas del tema**;
  - unas 7 son anuncios de servicios para gestorías («Stop chasing files via email»);
  - 8 son spam de los archivos Epstein («EFTA….jpg»);
  - el resto son noticias y política («papeles del contable» de Bárcenas, «documentos pendientes» de Epstein, el 23-F).
- **Por qué:** Bluesky solo busca las palabras y exige todas. «documentos pendientes», «papeles contable» y «tax documents clients» son frases de periódico. El cupo de 250 por fuente cuenta piezas traídas, no piezas del tema, así que el ruido se lo come entero.
- **Propuesta:** sale de las del punto 3. Con A, el ruido no llega a quejas; con B, además, que el cupo cuente solo lo que nombra el tema. Sin decisión, no toco Bluesky.

## Datos guardados con identificadores (R9, no corregidos)

- `niche_verdicts`: 23 de 80 tienen el DID en la clave del grupo. 2 lo enseñaban como nombre; desde af3644c ya no se enseña.
- 824 piezas de Bluesky llevan el DID en el id y en la dirección.
- El dossier guardado tiene 22 DID, todos en direcciones de Bluesky.
- 112 textos de evidencia tienen @usuario; desde af3644c se ocultan al enseñarlos.
- **Decisión pendiente (R5 frente a R9):** la dirección pública de un post de Bluesky necesita el DID o el @usuario. Opciones:
  - enseñar la dirección tal cual (hoy);
  - no enseñar la dirección de Bluesky, solo «Bluesky · fecha»;
  - cambiar el id del adaptador y migrar las 824 filas.

---

# Tras las decisiones de Walter (25-09): medidas A y B, cupo y umbral

Rama `fase3/tema`, sin fusionar. Cero Gemini y cero escaneos.

## Umbral 0,85: no aplicado, vuelve a Walter

Walter aprobó 0,85 «solo después de A + B, volviendo a medir». Resultado:

- **Escaneo 2 relabelado sin Gemini: no se puede.** labels-v5 decide «del tema»
  con el modelo; sin Gemini no hay etiqueta nueva. Solo se mide con el dorado.
- **El dorado tiene dos versiones**, y mi informe anterior solo enseñó v2:

| Umbral | v1 (6 subproblemas, 68 ítems): grupos · pureza · ARI | v2 (+4 vecinos): grupos · pureza · ARI |
|---|---|---|
| 0,82 (hoy) | 6 · 0,735 · **0,487** | 10 · 0,556 · 0,268 |
| 0,83 | 8 · 0,824 · 0,351 | 12 · 0,667 · 0,225 |
| 0,84 | 7 · 0,868 · 0,276 | 11 · 0,750 · 0,193 |
| 0,85 (aprobado) | 5 · 0,897 · **0,152** | 11 · 0,824 · 0,183 |
| 0,86 | 5 · 0,956 · 0,132 | 9 · 0,870 · 0,164 |

A 0,85 la pureza sube en los dos, pero en v1 el ARI cae un 69 %: los seis
subproblemas se rompen en trozos sueltos. Es un coste que Walter no vio al
aprobar. No cambio el umbral sin su decisión:

- **A. 0,85 igualmente**, aceptando ARI 0,152 en v1. Los suelos de
  `test_judge_cluster_calibration` bajan a lo medido.
- **B. 0,83:** pureza +0,089 en v1 y +0,111 en v2; ARI −0,136 y −0,043.
- **C. Dejar 0,82** y medir tras el primer escaneo con labels-v5. Si las quejas
  ya son del tema, el umbral tiene menos ruido que separar.

**Corrección mía:** dije que el comentario de `clustering.py` estaba desfasado
(pureza 0,735). No lo estaba: eran las cifras de v1. Era incompleto. Ahora da v1
y v2.

## Comunidades para temas de negocio y contabilidad (propuesta, sin construir)

**No verificado:** no he llamado a ningún foro ni instancia (cero escaneos).
Antes de añadir nada hay que comprobar que existen, que tienen API pública y
que tienen actividad.

**Discourse** (`RIR_DISCOURSE_FORUMS`; hoy manager.io, invoiceninja y
quickfile, todos de facturación):

- `discuss.frappe.io`: ERPNext, contabilidad de pymes; en inglés.
- `community.tillerhq.com`: hojas de cálculo de finanzas y contabilidad
  personal y de autónomos.
- Mismo criterio para cualquier otro: foros de programas de contabilidad o
  facturación donde la gente cuenta cómo trabaja, no foros de desarrollo.

**Mastodon** (hoy una sola instancia con búsqueda de texto completo, que solo
indexa lo que la instancia permite):

- Añadir la línea de tiempo por etiqueta (`/api/v1/timelines/tag/<etiqueta>`,
  pública) con etiquetas por tipo de tema. Negocio: #accounting,
  #bookkeeping, #smallbusiness, #freelance, #contabilidad, #autonomos,
  #pymes.
- Encaja con la medida B: el tipo de tema elegiría las etiquetas, como hoy
  elige los sitios de Stack Exchange.
