# Plan de Ejecución: Reddit Intelligence Radar

## Tareas Desglosadas

### Tarea 1: Consolidación de la Lista de Repositorios (Base + Expansión Diferencial)
- Definir la matriz completa de repositorios (Base de 28 proyectos explícitos + repos de social listening/leads + repositorios de expansión diferencial con valor técnico comprobado).
- Metadatos por repositorio: Slug, URL, Categoría Técnica, Técnica Diferencial Hipotética.

### Tarea 2: Desarrollo del Orquestador de Clonación (`scripts/clone_manager.py`)
- Soporte para clonación superficial (`--depth 1`).
- Manejo de excepciones (red, repo renombrado/archivado/privado).
- Persistencia de estado en `logs/clone_results.json` para ejecución resiliente y reanudable.
- Registro detallado de fallos en `logs/errors.log`.

### Tarea 3: Ejecución de la Descarga Controlada
- Ejecutar el script de clonación sobre `F:\reddit_intelligence_radar\repos\`.
- Supervisar progreso y capturar cualquier incidencia.

### Tarea 4: Desarrollo del Analizador de Repositorios (`scripts/repo_analyzer.py`)
- Inspección automática de directorios y archivos en cada repositorio clonado.
- Detección de archivos clave reales (parsers, prompts, scripts de extracción, modelos de clustering, APIs).
- Generación de rutas relativas verificadas.

### Tarea 5: Generación del Índice Maestro (`F:\reddit_intelligence_radar\INDEX.md`)
- Crear el archivo maestro con la tabla requerida:
  `| Nombre del Proyecto | URL | Técnica Única que Aporta | Archivos/Módulos Clave para Estudiar |`
- Agregar secciones complementarias organizadas por categoría técnica y arquitectura de referencia para facilitar la ingeniería inversa.

### Tarea 6: Suite de Validación y Pruebas (`scripts/test_radar.py`)
- Verificar que las carpetas clonadas no estén vacías.
- Validar que cada archivo clave listado en `INDEX.md` exista físicamente en disco.
- Comprobar la integridad sintáctica de `INDEX.md`.

### Tarea 7: Revisión de Calidad y Cierre de Entrega (`/review` y `/ship`)
- Auditoría de espacio ocupado, estadísticas de repositorios exitosos vs. omitidos.
- Presentación ejecutiva y técnica al usuario.
