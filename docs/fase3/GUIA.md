# Fase 3 · Guía para validar SENTRA

Esta guía es para ti, Walter. Vas a hacer 3 o 4 escaneos de temas distintos y a leer la evidencia de cada veredicto. Lo que veas lo anotas en `REGISTRO.md`.

## 1. Antes de empezar

- Abre SENTRA desde el acceso del escritorio.
- En la barra de la izquierda, abajo, «Base de datos» y «Motor» tienen que estar en verde.
- En **Configuración › Gemini y presupuesto** mira «Gastado hoy». Cada día (hora de Lima) tienes **40 llamadas a Gemini**. Un escaneo puede usar **hasta 20**.
- Consejo: **2 escaneos por día como mucho**. Así nunca te quedas a medias por el tope.

## 2. Lanzar un escaneo (pantalla «Nuevo escaneo»)

1. **Tema.** Escribe el problema como se lo contarías a alguien («clientes que pagan tarde»), no el producto. Deja marcados **Español e Inglés** y **1 año**. Pulsa «Siguiente».
2. **Palabras clave.** Tienes dos formas de llenarlas:
   - Escríbelas tú y pulsa Intro. **No cuesta nada.**
   - Pulsa «Proponer palabras». **Cuesta 1 llamada a Gemini** y luego puedes quitar o añadir.

   Cuando el aviso diga **«Buena variedad»**, sigue. Eso son al menos 6 palabras, con 3 o más en cada idioma. Si dice «Pocas palabras», añade más, sobre todo en inglés.
3. **Revisar y escanear.** Mira la tarjeta «Lo que costará en Gemini» y pulsa «Escanear».

   Hoy la estimación dice **0–19 llamadas y 0–475 000 unidades de texto por escaneo**. La medí el 25-09 en el paso 3, con 7 palabras. Es un máximo: el motor para solo al llegar a un tope.

Mientras escanea puedes cambiar de pantalla. Si terminas fuera, «Nuevo escaneo» se marca con un punto.

## 3. Cuánto gasta cada cosa en Gemini

| Acción | Llamadas | Cuándo |
|---|---|---|
| Proponer palabras | 1 | Solo si pulsas el botón |
| Escanear | 0 a 19 (estimado; tope de 20) | Solo al pulsar «Escanear» |
| Dossier de un nicho | 1 (≈ 5 000 unidades; medido: 5 009 y 4 789) | Solo la primera vez. Luego dice «Guardado: se abre sin gastar» |
| Plan de construcción | 1 | Igual que el dossier |
| Abrir el Radar, las fichas, la búsqueda o las fuentes | 0 | — |

## 4. Leer el resultado

Al terminar, la pantalla dice **qué pasó, qué significa y qué hacer ahora**:

- **Hay un nicho para construir / prometedor.** Pulsa «Ver nicho».
- **Esta vez no hay nicho.** No es un error. Mira las cifras (comentarios leídos, con queja real, personas necesarias) y sigue el primer paso que propone.
- **3 grupos descartados** (plegado). Por qué no son nicho, en una frase cada uno.

## 5. Leer la evidencia de un veredicto (ficha del nicho)

En el Radar, «Ver nicho». Revisa en este orden:

1. **Veredicto y su porqué.** Arriba: Construir, Investigar más o Descartar, con una frase que dice por qué.
2. **Métricas.** Cuántas **personas distintas** se quejan (hacen falta al menos 5) y la puntuación.
3. **Algunas quejas.** Tres citas con su fuente y su dirección. La ventana no abre enlaces: **selecciona la dirección, cópiala y ábrela en tu navegador**. Comprueba que la cita existe y que habla del problema.
4. **Dossier.** «Guardar como PDF» o «como texto». Lista todas las quejas con su fuente. Ahí es donde se ve si la evidencia es real o ruido.
5. **Ver detalle** (abajo, plegado). Las pruebas del juez una a una, por si algo no te cuadra.

Qué buscar al leer:

- ¿Las quejas son de **personas distintas** o de la misma repetida?
- ¿Hablan del **mismo problema** o de cosas parecidas mezcladas?
- ¿Son **quejas** o son anuncios de alguien vendiendo su herramienta?
- ¿Alguien dice que **ya lo resuelve** una herramienta gratis? El juez lo castiga (regla de 3 personas).

## 6. Si algo falla

- **Una fuente falla.** Las demás siguen. «Ver detalle» dice el código; anótalo.
- **«Hoy no queda presupuesto de Gemini».** Espera a mañana o sube el tope en Configuración.
- **Reddit no se usa:** espera aprobación. **X está apagada.**
