# Fase 3 · Diagnóstico: fuentes en cero en el escaneo 1

Escaneo del 25-09 a las 15:53 (Lima), ejecución `01a0da57-de68-7fc9-86e3-032b130bf37b`, «Convertir un PDF a Word sin perder el formato».

- **Palabras:** las propuso Gemini. 7 en español y 7 en inglés, **todas de 4 a 6 palabras** («pdf to word ruins formatting», «pdf a word pierde formato»).
- **Ventana:** 90 días.
- **Resultado:** 512 traídas y 462 únicas. El juez guardó 35 (347 fuera de tema, 78 muy cortas, 2 spam), 5 con queja real y 0 nichos.

**Método.**
- Peticiones reales del motor, sacadas de `sidecar.log`.
- Resultado de cada fuente en `run_source_outcomes` y evidencia guardada, en solo lectura.
- Llamadas directas y gratuitas a cada API **antes de cualquier filtro de SENTRA**, con lo enviado y con variantes. Sin YouTube, sin Gemini y sin escanear.

## Fuente por fuente

| Fuente | Qué se envió | Qué devolvió la API antes de filtrar | Dónde se perdió | Causa |
|---|---|---|---|---|
| Hacker News | La palabra larga + una frase de queja. A palabras españolas se les pegaron frases inglesas («pdf a word pierde formato **is there an app**») | 0 en las 25 peticiones. Con la palabra enviada sola: 0 (90 d) y 2 (365 d). **«pdf to word»: 215 (90 d) y 771 (365 d)**. «pdf to word is there an app»: 37 | En la **búsqueda** | Palabra demasiado larga (Algolia exige todas las palabras) **y** frases de queja del otro idioma |
| Stack Exchange | La palabra larga, solo en `stackoverflow` | 0. **«pdf to word»: 1 (90 d) y 25 (365 d)**; en superuser, 8 (365 d) | En la **búsqueda** | Palabra demasiado larga. Además, el tema es de ofimática y Stack Overflow es de programación: hay poco aunque la palabra sea corta |
| GitHub | La palabra entre comillas (frase exacta) | 0. Sin comillas: 5. **«pdf to word» exacta: 681** (90 d) | En la **búsqueda** | Frase exacta de 4-6 palabras: casi nunca coincide. Con términos cortos, las comillas dan precisión y se mantienen |
| Discourse | La palabra larga en 3 foros de facturación (manager.io, invoiceninja, quickfile) | 0. «pdf to word»: 50 por foro, **pero de 150 temas solo 4 hablan de pasar PDF a Word**, todos de exportar facturas | En la **búsqueda**, y aunque la búsqueda fuera buena, **no hay contenido** | Los foros configurados son de facturación: para este tema el 0 es real. **No se toca** |
| Product Hunt | Busca *temas* («productivity») con cada palabra | Temas para la palabra larga: ninguno. Para «pdf to word», «pdf» o «PDF Editor»: ninguno. Para «productivity» o «developer tools»: sí | En la **búsqueda de temas** | La API no busca texto libre, solo categorías amplias. Para este tema el 0 es real. **No se toca** |
| Bluesky | La palabra larga (exige todas las palabras) | 1 guardada | En la **búsqueda** | Palabra demasiado larga. No se midió aparte: solo se buscaba con sesión |
| Mastodon | La palabra larga (exige todas las palabras) | 11 guardadas | En la **búsqueda** | Igual que Bluesky |
| YouTube | La palabra larga + frase de queja; 8 vídeos por búsqueda y 50 comentarios de cada uno | 500 guardadas (tope) de solo **21 vídeos**; 50 duplicadas y 236 muy cortas | En el **filtro del juez**: 347 fuera de tema y 78 muy cortas | Llenó el tope con 2 o 3 búsquedas: las demás palabras no llegaron a buscarse (reparto, sección siguiente) |

En ningún caso el 0 lo explican la ventana de fechas, el filtro de idioma ni los duplicados. Todo se pierde en la búsqueda, antes de llegar a SENTRA. La ventana sí multiplica: en HN, 90 días dan 215 y 365 días, 771.

## Arreglos (rama `fase3/fuentes-en-cero`, un commit por causa)

1. **Palabras propuestas de 1 a 3 palabras**, no frases de queja: Gemini y el respaldo sin Gemini. Las frases de queja ya las añade la biblioteca aparte.
2. **El idioma de cada palabra viaja con el perfil.** Es el de su fila en el asistente, y así no se pegan frases de queja de otro idioma.
3. **Aviso de búsquedas largas** en el paso 2, para las que escribe la persona. Arregla también «en español ni en inglés».

## Propuesta, sin construir: que una fuente no se coma el escaneo

1. **Tope de cada fuente proporcional.** Por ejemplo, ninguna fuente pasa de un tercio de lo que va al juez: con 500 piezas, 165 como mucho. Lo que sobra se descarta por fecha o relevancia *antes* de etiquetar, no después.
2. **YouTube, más ancho y menos hondo.** 10 comentarios por vídeo (los más relevantes) en lugar de 50, y más vídeos. Recorrer todas las palabras antes de repetir, como las demás fuentes, en vez de agotar el tope con las dos primeras búsquedas.
3. **YouTube, filtro de tema al traer.** Aplicar `menciona_el_tema` (ya existe) a cada comentario antes de contarlo en el tope. Hoy los «¡gracias!» de un tutorial gastan tope y luego el juez los tira (347 fuera de tema).
4. **En el resultado, cuánto aportó cada fuente.** Que la pantalla avise cuando una sola aporta más de la mitad: «Casi todo viene de YouTube: el resultado puede estar sesgado».

Walter decide cuáles y en qué orden. Cada uno lleva su test y su medida.

## Estimación para un nuevo escaneo del mismo tema

Esta estimación **no está verificada**: la comprobación la hace Walter con un escaneo real.

- Con palabras cortas (medido en las APIs, antes de los filtros de SENTRA), **HN, GitHub y Stack Exchange pasan de 0 a resultados**:
  - HN: ~20–40 por pareja de palabra y queja (90 días).
  - GitHub: cientos, pero sobre todo de librerías de PDF: al juez le llegará mucho fuera de tema.
  - Stack Exchange: pocos.
- Bluesky y Mastodon deberían subir de 12 a unas decenas.
- Discourse y Product Hunt seguirán en ~0 para este tema: el contenido no está ahí.
- **Mi estimación:** la evidencia que no es de YouTube pasa de 12 a entre 150 y 400 piezas, y YouTube sigue llenando su tope de 500 hasta que se aplique el reparto de arriba.
- Con 1 año en lugar de 3 meses, multiplica por unas 3,5 veces en HN.
- El veredicto esperado sigue siendo DESCARTAR: hay mucha herramienta gratuita recomendada. Ahora habría evidencia de varias fuentes para decidirlo.
