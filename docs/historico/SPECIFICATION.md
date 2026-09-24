# Especificación Técnica: Reddit Intelligence Radar (F:\reddit_intelligence_radar)

## 1. Visión General y Objetivo
Construir y organizar en el disco `F:\` una biblioteca de referencia exhaustiva y de ingeniería inversa orientada a la extracción de inteligencia en Reddit, minería de problemas/puntos de dolor (*pain points*), prospección automatizada de leads con intención de compra y validación acelerada de micro-SaaS.

## 2. Requerimientos Funcionales y No Funcionales
1. **Directorio Base**: `F:\reddit_intelligence_radar\repos\`
2. **Estrategia de Clonación**:
   - Clonación superficial (`git clone --depth 1 <url>`) para optimizar tiempo de red y espacio.
   - Resiliencia ante fallos: Detección y manejo de repositorios eliminados, renombrados, privados o archivados sin abortar el proceso.
   - Registro de incidencias en `logs/errors.log` y estado de descarga en `logs/clone_results.json`.
3. **Criterio de Inclusión y Curaduría**:
   - **Lista Base**: Los repositorios fundamentales definidos en el requerimiento del usuario (PRAW, reddit-painpointer, Scrapegraph-ai, Litellm, Atalaia, etc.).
   - **Expansión Inteligente Diferencial**: Incorporación de repositorios open-source adicionales que aporten técnicas *únicas* comprobadas (p. ej., agentes MCP para Reddit, clustering con BERTopic, parsers directos JSON/RSS sin API key, matrices de Willingness-To-Pay, filtros de intención de compra con LLMs).
4. **Análisis y Documentación**:
   - Inspección estática del árbol de código de cada repositorio descargado para ubicar los archivos y módulos exactos donde reside la técnica diferencial.
   - Generación de `INDEX.md` con tabla Markdown estandarizada:
     `| Nombre del Proyecto | URL | Técnica Única que Aporta | Archivos/Módulos Clave para Estudiar |`

## 3. Arquitectura del Entorno
```
F:\reddit_intelligence_radar\
├── INDEX.md                 # Catálogo maestro de consulta rápida y técnica diferencial
├── SPECIFICATION.md         # Documento de especificación de arquitectura y alcance
├── PLAN.md                  # Desglose de tareas y dependencias lógicas
├── logs\
│   ├── clone_results.json   # Metadatos de ejecución por repositorio
│   └── errors.log           # Bitácora de incidencias o repos no disponibles
├── scripts\
│   ├── clone_manager.py     # Script autónomo de orquestación de clonación y reintentos
│   ├── repo_analyzer.py     # Analizador de árboles de código y extracción de rutas clave
│   └── generate_index.py    # Generador automatizado del archivo INDEX.md
└── repos\
    ├── <owner>__<repo> / <repo>   # Proyectos clonados
```

## 4. Criterios de Aceptación y Validación
- Todos los repositorios alcanzables de la lista base y de la expansión curada deben estar clonados en `F:\reddit_intelligence_radar\repos\`.
- Cada repositorio debe contener sus archivos de código fuente inspeccionables.
- El archivo `INDEX.md` debe contener una fila detallada por cada proyecto con URLs exactas, técnica diferencial clara y rutas reales de archivos clave.
- Las incidencias de repositorios inaccesibles o renombrados deben estar claramente documentadas y categorizadas en `errors.log`.
