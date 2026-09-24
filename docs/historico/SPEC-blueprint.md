# Spec: resiliencia de la UI + Generador de Especificación de Proyecto (PRD)

Fecha: 2026-09-21. Estado: aprobada por defecto (ver "Asunciones").

## Mapa de capacidades

| Módulo id        | Responsabilidad                                              | Depende de |
|------------------|--------------------------------------------------------------|------------|
| `ui-resiliencia` | Que un fallo en una vista no deje la ventana en blanco        | —          |
| `blueprint`      | Sintetizar un PRD a partir de la evidencia de un cluster      | —          |

Orden de construcción: `ui-resiliencia` → `blueprint`.
Son independientes: cada uno se puede verificar y entregar por separado. Se hace
primero la resiliencia porque es la red que protege al segundo mientras se prueba.

## Asunciones (declaradas, no consultadas)

1. **No hay modelo de lenguaje en el proyecto.** No existe clave de API ni modelo
   generativo local. El sintetizador es **determinista**: deriva cada frase de la
   evidencia guardada (keywords, `job_statement`, citas, factores de puntuación) con
   reglas y plantillas. No inventa datos. Un PRD que rellenara huecos con prosa
   plausible sería placebo, y este proyecto no lo admite.
2. **"Competidores fallidos" = `current_solutions`.** No existe columna
   `competitors_mentioned`; lo que el motor extrae son los apaños y herramientas que
   la gente cita. En el corpus de demostración viene **vacío**, así que esa sección
   debe degradar con elegancia y decir que no hay datos, nunca inventarlos (deuda D10).
3. **La fuente de verdad es PostgreSQL**, no el estado del navegador: el documento se
   genera desde el cluster leído de la base, para que no dependa de lo que la ventana
   tuviera cargado.
4. **El idioma lo decide quien mira**, y viaja como parámetro (`es` | `en`).

## Objetivo

- `ui-resiliencia`: ningún error de render puede vaciar la ventana. Debe verse qué
  falló y poder volver.
- `blueprint`: convertir un cluster de quejas en un documento que un equipo pueda
  leer y ejecutar, entendible por alguien sin contexto técnico y con suficiente
  detalle para ingeniería.

## Contrato del documento

```
BlueprintDoc
  productName      str        nombre conceptual derivado de las keywords
  oneLiner         str        propuesta de valor en una frase
  executiveSummary str        qué problema resuelve y para quién
  problem          Section    dolores + volumen real de evidencia citado
  solution         Section    qué construir
  mvp              Phase[]    fase 1 indispensable / fase 2
  whyExistingFail  Section    apaños citados, o ausencia explícita de datos
  monetisation     Section    modelo sugerido según la señal de pago detectada
  evidence         Quote[]    citas textuales deduplicadas
  markdown         str        el documento entero, listo para copiar
```

## Comandos

```
Tests Python:  python -m unittest discover -s tests -p "test_*.py"
Tests Rust:    cargo test            (en ui/src-tauri)
Build UI:      npm run build         (en ui)
Check Rust:    cargo check --all-targets
```

## Estructura

```
core/intelligence/blueprint.py      sintetizador (sin E/S, puro)
tests/test_blueprint.py             tests del sintetizador
core/orchestration/sidecar_server.py  endpoint POST /api/blueprint
ui/src-tauri/src/commands/blueprint.rs  comando Tauri (lee PG -> sidecar)
ui/src/components/ErrorBoundary.tsx  red de seguridad de render
ui/src/components/BlueprintPanel.tsx panel del documento
```

## Estrategia de pruebas

`unittest`, en `tests/`. El sintetizador es puro, así que se prueba con clusters
construidos a mano. Casos obligatorios:

- Un cluster con evidencia completa produce todas las secciones.
- **Sin `current_solutions`**, la sección de competencia dice que no hay datos y no
  inventa nombres.
- Citas idénticas repetidas se deduplican (el corpus de demostración repite la misma).
- La señal de pago alta y la nula producen recomendaciones de monetización distintas.
- El Markdown generado contiene el volumen real de menciones y comunidades.
- El idioma `en` no deja frases en español sueltas.

## Límites

- **Siempre:** citar volumen real; test antes que código; secretos fuera del documento.
- **Preguntar antes:** cambiar el esquema de la base; añadir dependencias.
- **Nunca:** inventar competidores, precios o métricas que la evidencia no respalde.

## Criterios de aceptación

1. Pulsar "Configuración" abre la vista y, si el motor no responde, se ve un aviso
   legible en lugar de una pantalla vacía.
2. Un error de render en cualquier vista muestra el `ErrorBoundary` con el mensaje y
   un botón para reintentar; la barra lateral sigue usable.
3. La ficha de oportunidad tiene un botón que despliega el PRD maquetado.
4. "Copiar en Markdown" deja el documento entero en el portapapeles.
5. Todo el texto nuevo existe en `es` y en `en`.
6. `npm run build` y `cargo check` sin errores; suite acumulada en verde.

## Preguntas abiertas

- El corpus sintético repite la misma queja 5 veces, así que "5 menciones" son un
  mismo texto. El documento dice cuántas citas **distintas** respaldan el caso para
  no exagerar la evidencia.
