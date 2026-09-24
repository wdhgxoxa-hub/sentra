# Plan: calidad por fuente, nuevo escaneo de facturación y E8 (2026-09-24)

Pedido del usuario tras el escaneo 01a0d475 («facturación para freelancers y
pequeños negocios»): 136 piezas, 83 % de YouTube (títulos y descripciones
promocionales), comentarios de HN fuera de tema, Bluesky y Mastodon con 0,
4 dolores y 0 nichos. Atacar la causa en cada fuente, medir cada una antes y
después (sin Gemini) y repetir el escaneo. Presupuesto de Gemini: quedan 9 de
15 llamadas.

## Causas medidas («antes», scratchpad/medida_antes.json)

- **Común.** `term_pairs` une cada palabra del tema con cada frase de
  intención sin mirar el idioma. Resultado: consultas como
  «facturación autónomos is there a tool».
- **Bluesky y Mastodon.** Exigen todas las palabras y la frase entre comillas:
  49 consultas, 0 resultados. Con consultas simples devuelven 20–25 por
  consulta (sondeo_social.py).
- **YouTube.** Cada búsqueda entrega sus 25 vídeos como piezas (título y
  descripción) y solo lee comentarios de 5. 103 vídeos y 12 comentarios; se
  agota el tope de 25 peticiones.
- **Hacker News.** Algolia devuelve coincidencias sueltas: comentarios cuyo
  texto no habla del tema.
- **Discourse.** Ningún foro configurado (`sin foros`).

## Tareas

- [x] F1 · Consultas por idioma: una palabra del tema solo se une a frases de
      su idioma. Acepta: ninguna consulta mezcla idiomas.
- [x] F2 · Bluesky y Mastodon buscan solo el tema (el juez filtra el dolor).
      Acepta: > 0 piezas con el mismo perfil.
- [x] F3 · YouTube trae comentarios, no vídeos:
      - videos.list (estadísticas) para elegir los vídeos con más comentarios;
      - el título del vídeo solo como contexto del comentario.
      Acepta: 0 piezas de tipo vídeo; comentarios > 0.
- [x] F4 · HN descarta comentarios cuyo texto no nombra el tema. Acepta: 0
      comentarios sin término del tema.
- [x] F5 · Discourse con foros de freelancers y pequeños negocios, verificados
      por su API (about.json) antes de guardarlos. Acepta: piezas > 0.
- [x] Medida «después» por fuente (mismo perfil y mismo script) y
      comparación.
- [x] Escaneo repetido con tope de 100 piezas etiquetadas (5 llamadas) + 1 de
      coherencia; quedan ≥ 3 para E8.
- [x] E8 si sale un nicho coherente; si no, se dice y no se genera nada.

## Resultado (2026-09-24)

Medida por fuente, mismo perfil y script (piezas · % del tema · 1.ª persona):

| Fuente | Antes | Después |
|---|---|---|
| Hacker News | 21 · 76 % · 13 | 11 · 91 % · 5 |
| YouTube | 118 (103 vídeos) · 81 % · 0 | 285 comentarios · 18 % · 9 |
| Bluesky | 0 | 326 · 77 % · 9 |
| Mastodon | 0 | 146 · 95 % · 28 |
| Discourse | 0 (sin foros) | 21 · 100 % · 6 |
| GitHub | 1 | 115 · 96,5 % · 14 |
| Stack Exchange | 1 | 1 |

Stack Exchange sigue en 1: no es la consulta, es el dato. Con el sitio por
defecto (stackoverflow) y sondeando money, superuser, freelancing, webapps,
softwarerecs y es.stackoverflow, el tema da 0–2 preguntas en 365 días.

Escaneo repetido (ejecución 01a0d4a5-add2-70d8-99e0-a860014ce170, release):
728 piezas, 627 conservadas, 116 etiquetadas (tope 100 nuevas + caché),
19 con dolor (Discourse 6, YouTube 6, Bluesky 4, HN 3, Mastodon 2, GitHub 1),
1 grupo, que G0 rechaza con razón: mezcla una plantilla de factura, clientes
que no pagan, el tedio administrativo del freelance, facturas recurrentes y
extraer PDF a Excel. DESCARTAR «sin problema común». 6 llamadas a Gemini.

E8: no hay nicho coherente, no se genera ningún documento.

## Tema estrecho: «clientes que no pagan facturas a freelancers» (2026-09-24)

Presupuesto nuevo: 40 llamadas. En dos fases para etiquetar todo bajo un tope duro:

1. Escaneo desde la release sin etiquetar (RIR_JUEZ_MAX_ETIQUETAS=0), ejecución
   01a0d4b7-01b1-7163-af6b-51472b5f2e8e: 679 piezas, 547 pasan el filtro. 0 llamadas.
2. `rejuzgar.py --max-llamadas 32 --max-etiquetas 547` (6d129bf), ejecución
   01a0d4c1-3093-783b-8030-0416a68ffdbb: 547 etiquetadas, 82 con dolor
   (YouTube 41, Bluesky 17, Mastodon 16, Discourse 5, GitHub 3). 28 llamadas.
   El informe de tokens se perdió: el script reventó al imprimirlo (8f5be0d lo arregla).

8 grupos, todos DESCARTAR: 7 no son un mismo problema (G0) y el único coherente
son 4 comentarios de YouTube sobre un vídeo con música alta (fallan G1 y G2).
Sin nicho: E8 no se hace. Quedan 12 de 40.

Diagnóstico (0 llamadas): hay ~15 quejas claras de impago de autores distintos,
sobre todo en Bluesky y Mastodon, y sus frases se parecen (similitud e5 mediana
0,842; mín. 0,783) por encima del umbral 0,82; pero en e5 frases sin relación
rondan 0,78, y con 41 dolores de YouTube que hablan del vídeo, los grupos salen
mezclados y G0 los rechaza. Causas candidatas: ruido de comentarios de YouTube
etiquetados como dolor y un umbral de agrupación poco discriminante.

## Ruido y umbral: criterios fijados ANTES de mirar el resultado real (2026-09-24)

Aviso de honestidad: el diagnóstico anterior ya enseñó la similitud de 11 frases
de impago (0,783–0,922). Por eso no se inventa un criterio nuevo: se usa el que
ya estaba escrito en scripts/calibrar_agrupacion.py desde B3.

- R1 · Ruido: con tema, un comentario (kind = comment) cuyo texto propio no
  nombra el tema (menciona_el_tema) no se etiqueta; cuenta como descartado
  «off_topic». Los posts no cambian. Sin tema, nada cambia.
- R2 · Umbral: se calibra SOLO con el conjunto dorado de frases
  (tests/fixtures/golden_clusters_e5.npz, mismo embedder que en ejecución),
  enlace promedio, rejilla 0,78–0,94 de 0,01. Criterio: ARI máximo; a igualdad,
  más pureza; a igualdad, el umbral más alto. Si sale 0,82, el umbral no cambia.
- Validación (impagos, re-juicio del escaneo 01a0d4b7…, etiquetas en caché;
  tope 4 llamadas): «coherente» = un grupo que pasa G0 con ≥ 3 autores distintos
  cuyo dolor es un impago (regex IMPAGO del diagnóstico). Si lo hay, E8: dossier;
  plan solo si el juez dice CONSTRUIR. Si no, se dice y no se genera nada.

### Resultado (criterios de arriba, sin tocarlos)

- R1 (012a4eb): 300 comentarios fuera de tema descartados; quedan 246, 51 con dolor.
- R2: el barrido del dorado vuelve a elegir 0,82 (ARI 0,487; 0,83 da pureza 0,824
  pero ARI 0,351). Umbral sin cambios; versión clustering-v8 por R1.
- Validación (re-juicio 01a0d4cc-34af-7049-9a1b-4d75bcc2c956, 1 llamada, 1468→326
  tokens): 3 grupos, los 3 fallan G0. El de impagos existe (~31 miembros, ~18
  quejas reales de impago de Bluesky, Mastodon, GitHub y Discourse) pero arrastra
  vecinos del mismo mundo (impuestos, QuickBooks, comentarios del cliente,
  conseguir clientes). No cumple el criterio: E8 no se hace. No se prueba otro
  umbral con este caso (sería calibrar con la validación).
- Gemini de este presupuesto: 29 de 40; quedan 11.

## Opción 1: dorado con subproblemas vecinos — diseño fijado ANTES de medir (2026-09-24)

- Se añade al dorado un segundo tema inventado (R8), «dinero del freelance», con
  cuatro subproblemas vecinos de 10 ítems (5 en, 5 es), mismo formato que los
  existentes: impagos (clientes que no pagan / perseguir facturas), impuestos
  (IVA, trimestrales, cuotas), captar clientes, y herramientas contables
  (conciliación bancaria, software que falla). Textos escritos de cero, no
  parafraseados de piezas reales. Los 68 ítems actuales no se tocan.
- Vectores con scripts/embed_golden_clusters.py (mismo embedder que en ejecución).
- Criterio del umbral: el mismo de siempre (ARI máximo; a igualdad, más pureza;
  a igualdad, el umbral más alto), enlace promedio, rejilla 0,78–0,94 de 0,01,
  sobre el dorado entero (108 ítems).
- Validación: la misma de antes (grupo que pasa G0 con ≥ 3 autores cuyo dolor es
  un impago). Si falla, opción 2 (G0 separa el problema dominante) con ≤ 8
  llamadas. Presupuesto: 11; E8 va con lo que quede (dossier primero).

### Resultado de la opción 1, la opción 2 y E8

- Anuncios (eef1705, clustering-v9): «problema → solución» en el texto es
  autopromoción: competencia, nunca dolor. Los dos anuncios de Bluesky, fuera.
- Opción 1 (0f725ce): dorado v2 con 40 ítems vecinos inventados; el criterio de
  siempre vuelve a elegir 0,82 (ARI 0,268). Validación (01a0d4e0…, 1 llamada):
  4 grupos, los 4 fallan G0. Falla.
- Opción 2 (9c193fd, coherence-v2, clustering-v10): G0 señala el problema
  dominante de una mezcla (≥ 3 frases), se separa y se confirma en otra llamada.
  Validación (01a0d4e6-b533-7d3e-a03a-4dd9580cba8d, 2 llamadas): 2 mezclas
  separadas; el subgrupo de impagos (9 autores; GitHub, Bluesky, Mastodon) pasa
  G0 en la confirmación. PASA. El juez lo deja en DESCARTAR por G7 (saturación),
  decidida por una sola pieza: un lanzamiento de HN de un asistente que «persigue
  facturas» (cuota 1/1 = 100 %).
- E8 (dossier; el plan exige CONSTRUIR): 1 llamada, gemini-3.1-pro-preview
  (Automático), 1293 → 1057 tokens (+2445 razonamiento), 11 secciones, 7 citas
  reales. Problemas: nombre «week, morning» (las palabras del tema se excluyen);
  prosa sin tildes; afirmaciones que generalizan una cita; riesgos vacíos; no
  explica G7 ni cita el lanzamiento que la decide.
- Gemini de este presupuesto: 33 de 40; quedan 7.

## Propuesta G7 (mínimo de menciones) — fijada ANTES de mirar datos (2026-09-24)

Hoy la cuota de G7 es, por competidor gratuito, menciones «satisfecho» / menciones:
con 1 sola mención favorable sale 100 % y DESCARTAR. Propuesta (pendiente del sí
del usuario; no se implementa ni se prueba contra datos hasta entonces):

- Un competidor cuenta para G7 solo si lo mencionan al menos 3 autores distintos
  (el mismo mínimo que usa el juez para llamar patrón a algo: MIN_CLUSTER_SIZE y
  MIN_DOMINANTES = 3). Con 3 o más, la regla de siempre (cuota > 0,5 falla).
- Con 1–2 menciones favorables de un competidor gratuito: G7 queda «sin datos
  suficientes» (no medida) con la nota y las piezas; no descarta, pero el
  veredicto no puede pasar de INVESTIGAR MÁS (señal sin resolver).
- Sin menciones: como hoy (aprueba por ausencia).

### Dossier corregido (debef47) y regenerado (1 llamada)

- 1 llamada, gemini-3.1-pro-preview, 1418 → 1096 tokens (+2321 razonamiento), 11 secciones.
- Título «Autónomos persiguiendo facturas impagadas» (propuesto por el modelo, dicho en la portada).
- Tildes correctas (0 palabras comunes sin tilde en la prosa).
- 4 afirmaciones marcadas «Anécdota (1 autor)» por el código; las generales citan ≥ 2 autores.
- Riesgos: G7 con la pieza que la decide (hackernews:47545486), citada en la evidencia.
- Queda: la línea de G7 da valor y umbral pero no lo explica en palabras; una
  afirmación que junta dos ideas puede colar la parte de un solo autor.
- Gemini: 34 de 40; quedan 6.

### Regla de competencia de 3 autores (aprobada, c7b1a39) y re-juicio

Re-juicio 01a0d538-75f4-721c-8802-513c0ebfff98 (2 llamadas, tope duro 2): el grupo
de impagos (9 autores, G0 pasa) pasa de DESCARTAR a INVESTIGAR MÁS por la regla 9:
G7 «menciones favorables insuficientes» (Clawbolt 1 de 3 autores, duevero.com 1 de
3). Los otros 3 grupos siguen siendo mezclas (G0). Gemini: 36 de 40; quedan 4.
Observación: el contexto de G7 (piezas sin dolor cercanas al grupo) es casi el
mismo para los cuatro grupos; no se ha tocado.

## Pendientes menores del dossier — criterio fijado ANTES de medir (2026-09-24)

1. La línea de G7 (y de cualquier compuerta en Riesgos) dice en palabras qué
   exige la compuerta y lleva su nota; sin llamadas.
2. Contexto de G7 (piezas sin dolor cercanas al grupo): hoy una pieza entra en el
   contexto de TODOS los grupos cuyo centro supera 0,82, y en un escaneo de un
   solo tema casi todas entran en todos. Criterio: cada pieza sin dolor va al
   contexto de UN solo grupo, el de centro más cercano, y solo si supera 0,82 (el
   umbral no cambia; no se calibra nada). Medida antes/después sin llamadas: piezas
   de contexto por grupo y cuántas comparten grupos, en el escaneo de impagos.

### Resultado (sin llamadas)

1. Riesgos en palabras (bf74e66): cada compuerta dice qué exige, con su nota.
2. Contexto de G7 (judge-weights-v6), impagos, antes → después:
   piezas de contexto por grupo 127/154/172/188 → 18/45/71/63; en más de un grupo
   179 de 197 → 0. G7 del grupo de impagos: sigue «insuficiente» (regla 9, INVESTIGAR
   MÁS), ahora solo por duevero.com (1 de 3); Clawbolt pasa al grupo de conciliación.
   Los veredictos guardados se calcularon con el contexto anterior; re-juzgar costaría
   2 llamadas y no cambia ningún veredicto (cambia la nota de G7).
   Re-juicio con la versión actual (01a0d587-e284-72cf-ba49-5cb0929e5e55, 2 llamadas):
   impagos INVESTIGAR MÁS por la regla 9, G7 solo por duevero.com (1 de 3), como se
   predijo sin llamadas. Los 4 veredictos llevan judge-weights-v6 · clustering-v10.
   Variación del LLM: el grupo «clients» (4 comentarios de YouTube) pasa ahora la
   confirmación de G0 y cae por la regla 3 (fallan G1 y G2). Gemini: 38 de 40.

## Nombre único y G0 estable — diseño y criterio fijados ANTES de medir (2026-09-24)

Decisión del usuario: temperatura por defecto (Google desaconseja < 1,0 en Gemini 3);
la estabilidad la da una caché de G0 por grupo.

- Migración 016 (R12): tabla coherence_checks (resultado de G0 por hash del grupo
  —pares id/frase ordenados— y versión del revisor) y niche_verdicts.problem_name
  (jsonb {es, en}, nulo en mezclas y veredictos antiguos).
- G0 (coherence-v3): si el grupo es un mismo problema, el modelo lo nombra en es y
  en en la misma llamada. Lo que está en caché no se pregunta; la confirmación de
  subgrupos también pasa por la caché.
- El Radar y el dossier leen el nombre del veredicto; el problem_name del dossier
  queda solo como respaldo de veredictos sin nombre.
- Medida (≤ 2 llamadas; quedan 2 de 40): re-juicio 1 de impagos (G0 + confirmación)
  llena la caché; re-juicio 2 con --max-llamadas 0. Estable = los dos dan los mismos
  grupos (miembros), el mismo G0 por grupo, los mismos nombres y los mismos
  veredictos, y el segundo hace 0 llamadas. La estabilidad intrínseca del modelo a
  temperatura por defecto NO se mide (haría falta repetir llamadas).
