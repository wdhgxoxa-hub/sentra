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
