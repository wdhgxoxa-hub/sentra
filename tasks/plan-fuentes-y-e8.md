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

- [ ] F1 · Consultas por idioma: una palabra del tema solo se une a frases de
      su idioma. Acepta: ninguna consulta mezcla idiomas.
- [ ] F2 · Bluesky y Mastodon buscan solo el tema (el juez filtra el dolor).
      Acepta: > 0 piezas con el mismo perfil.
- [ ] F3 · YouTube trae comentarios, no vídeos:
      - videos.list (estadísticas) para elegir los vídeos con más comentarios;
      - el título del vídeo solo como contexto del comentario.
      Acepta: 0 piezas de tipo vídeo; comentarios > 0.
- [ ] F4 · HN descarta comentarios cuyo texto no nombra el tema. Acepta: 0
      comentarios sin término del tema.
- [ ] F5 · Discourse con foros de freelancers y pequeños negocios, verificados
      por su API (about.json) antes de guardarlos. Acepta: piezas > 0.
- [ ] Medida «después» por fuente (mismo perfil y mismo script) y
      comparación.
- [ ] Escaneo repetido con tope de 100 piezas etiquetadas (5 llamadas) + 1 de
      coherencia; quedan ≥ 3 para E8.
- [ ] E8 si sale un nicho coherente; si no, se dice y no se genera nada.
