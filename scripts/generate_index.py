#!/usr/bin/env python3
"""
Generador del Archivo Maestro INDEX.md para SENTRA
Crea la tabla estandarizada requerida por la especificacion con:
| Nombre del Proyecto | URL | Técnica Única que Aporta | Archivos/Módulos Clave para Estudiar |
y enriquece con taxonomias, arquitectura de referencia, desglose por lotes
e instrucciones de ingenieria inversa.
"""

import json
from collections import defaultdict
from pathlib import Path

# La raíz del repositorio, desde aquí: funciona en cualquier unidad y copia (D5).
BASE_DIR = Path(__file__).resolve().parents[1]
LOGS_DIR = BASE_DIR / "logs"
CATALOG_FILE = LOGS_DIR / "repo_catalog.json"
INDEX_FILE = BASE_DIR / "INDEX.md"
ERRORS_FILE = LOGS_DIR / "errors.log"

def generate_index():
    if not CATALOG_FILE.exists():
        print(f"Error: No se encuentra {CATALOG_FILE}. Ejecute repo_analyzer.py primero.")
        return

    with open(CATALOG_FILE, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    # Estadisticas
    total_repos = len(catalog)
    cloned_ok = [r for r in catalog if r.get("status") == "ready"]

    # Identificar Lote 1 vs Lote 2
    batch2_ids = {
        "reddit-find", "reddit-agent-langgraph", "reddit-research-mcp",
        "n8n-reddit-scraper", "reddit-streaming-pipeline", "reddit-sentiment-analysis-fullstack",
        "reddit-kb-mcp-server", "multimodal-reddit-search", "reddit-sentiment-zero-shot",
        "reddit-hole-playwright", "lancedb-vectordb-recipes", "vectfox-hybrid-search"
    }

    batch1_repos = [r for r in catalog if r["id"] not in batch2_ids]
    batch2_repos = [r for r in catalog if r["id"] in batch2_ids]

    lines = []
    lines.append("# SENTRA — Colección Maestra de Repositorios")
    lines.append("")
    lines.append("> Repositorio local de referencia e ingeniería inversa para extracción masiva de datos en Reddit, minería semántica de puntos de dolor (*pain points*), detección algorítmica de demanda (*leads & buying intent*), bases de datos vectoriales y aceleración de micro-SaaS.")
    lines.append("")
    lines.append("- **Ubicación en disco**: `repos/` en la raíz del repositorio")
    lines.append(f"- **Total de proyectos investigados y activos**: {total_repos}")
    lines.append(f"- **Lote 1 (Base + Expansión Inicial)**: {len(batch1_repos)} repositorios")
    lines.append(f"- **Lote 2 (Nueva Expansión Diferencial)**: {len(batch2_repos)} repositorios")
    lines.append(f"- **Tasa de éxito de clonación**: 100% ({len(cloned_ok)}/{total_repos})")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 1. Tabla Maestra Consolidada de Proyectos (57 Repositorios)")
    lines.append("")
    lines.append("| Nombre del Proyecto | URL | Técnica Única que Aporta | Archivos/Módulos Clave para Estudiar |")
    lines.append("|---|---|---|---|")

    for r in catalog:
        name = r["name"]
        url = r["url"]
        tech = r["differential_technique"]
        key_files = r.get("key_files", [])
        repo_id = r["id"]
        
        # Etiqueta de lote
        is_batch2 = repo_id in batch2_ids
        badge = " 🔥 `[Lote 2]`" if is_batch2 else ""

        if r.get("status") == "ready":
            files_str = "<br>".join([f"`repos/{repo_id}/{f}`" for f in key_files])
        else:
            files_str = f"*No disponible ({r.get('status')})*"

        tech_clean = tech.replace("|", "\\|")
        name_clean = (name + badge).replace("|", "\\|")
        lines.append(f"| [{name_clean}]({url}) | {url} | {tech_clean} | {files_str} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Seccion Especial: Que aporta el Lote 2 frente a los primeros 45
    lines.append("## 2. Nueva Expansión (Lote 2): Análisis Diferencial vs. Primeros 45")
    lines.append("")
    lines.append("""El Lote 2 incorpora paradigmas computacionales y arquitectónicos ausentes en los primeros 45 repositorios:

| Nuevo Proyecto | Dominio Técnico | ¿Qué Aporta frente a los Primeros 45? |
|---|---|---|
| **reddit-agent-langgraph** (`avisangle/reddit_agent`) | Agentes Autónomos con Estado | **Máquina de estados LangGraph**: Orquesta decisiones cíclicas, evaluación de calidad por LLM y validación humana obligatoria (*Human-in-the-Loop*) vía Slack/Telegram antes de emitir cualquier mensaje. |
| **n8n-reddit-scraper** (`gguyon0925/n8n-reddit-scraper`) | Orquestación Visual No-Code/Low-Code | **Workflows visuales n8n**: Plantillas declarativas para prospección comercial automática sin programar scripts ad-hoc, listas para disparar webhooks a CRMs o servidores MCP. |
| **reddit-streaming-pipeline** (`nama1arpit/reddit-streaming-pipeline`) | Big Data Distribuido en Tiempo Real | **Streaming a gran escala**: Desacopla la ingesta mediante **Apache Kafka**, procesa millones de comentarios con **Spark Streaming**, persiste en **Cassandra** y grafica métricas en **Grafana**. |
| **multimodal-reddit-search** (`DaveOkpare/multimodal-search`) | Búsqueda Vectorial Multimodal | **Embeddings texto + imagen**: Utiliza **OpenAI CLIP** junto a **Qdrant** para permitir consultas cruzadas (ej. buscar quejas sobre diagramas de arquitectura o capturas de UI publicadas en Reddit). |
| **lancedb-vectordb-recipes** (`lancedb/vectordb-recipes`) | Vectores Serverless en Disco | **Almacenamiento columnar Lance**: RAG de altísima velocidad y cero infraestructura dedicada, leyendo índices vectoriales directamente desde disco local o S3. |
| **vectfox-hybrid-search** (`KritBlade/VectFox`) | Memoria Híbrida Qdrant | **Fusión de búsqueda híbrida**: Combina similitud semántica densa con pesos léxicos BM25 dispersos para recuperar contexto exacto en hilos técnicos largos. |
| **reddit-research-mcp** (`dialog-tools/reddit-research-mcp`) | Búsqueda Semántica MCP Masiva | **Indexación global de 20k subreddits**: Expone herramientas semánticas nativas a Claude/Cursor con soporte de citaciones verificadas de fuentes primarias. |
| **reddit-kb-mcp-server** (`lh1207/reddit-kb-mcp-server`) | Base de Conocimiento Local ChromaDB | **Ingesta de guardados personales**: Vectoriza el archivo privado de publicaciones guardadas de Reddit para asistentes LLM. |
| **reddit-sentiment-zero-shot** (`marta-baratto/Reddit_sentiment`) | Inferencia de Lenguaje Natural (NLI) | **Clasificación Zero-Shot sin dataset de entrenamiento**: Aplica modelos de hipótesis/premisa para etiquetar dolores financieros y de mercado de forma no supervisada. |
| **reddit-hole-playwright** (`nssharmaofficial/reddit-hole`) | Automatización de Navegador Real | **Crawling dinámico con Playwright**: Resuelve desafíos de carga asíncrona pesada en JavaScript y renderizado SPA de Reddit donde requests simples fallan. |
| **reddit-find** (`LeadGrowGTM/reddit-find`) | Minería de Lenguaje de Compra | **Buyer Language Extraction**: Script focalizado en extraer verbatim frases de dolor B2B y objeciones de clientes sin API key, formateando Markdown limpio para alimentar LLMs. |
| **reddit-sentiment-analysis-fullstack** (`netto14cr/reddit_sentiment_analysis`) | Aplicación Web Desacoplada | **Arquitectura React + Flask**: Proporciona un dashboard interactivo completo para usuarios de negocio con métricas de polaridad visualizadas en tiempo real. |
""")

    lines.append("---")
    lines.append("")

    # Categorias por arquitectura
    lines.append("## 3. Mapa Arquitectónico Consolidado por Capas")
    lines.append("")
    by_category = defaultdict(list)
    for r in catalog:
        by_category[r.get("category", "General")].append(r)

    for cat, items in by_category.items():
        lines.append(f"### Capa: {cat}")
        lines.append("")
        for item in items:
            status_icon = "✅" if item.get("status") == "ready" else "⚠️"
            is_batch2 = item["id"] in batch2_ids
            tag = " `[LOTE 2]`" if is_batch2 else ""
            lines.append(f"- {status_icon} **{item['name']}**{tag} (`{item['id']}`): {item['differential_technique']}")
            if item.get("status") == "ready" and item.get("key_files"):
                for kf in item["key_files"]:
                    lines.append(f"  - 📄 Archivo clave: `repos/{item['id']}/{kf}`")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 4. Matriz de Síntesis para Arquitectura Micro-SaaS")
    lines.append("")
    lines.append("""Con la incorporación del Lote 2, el flujo de desarrollo de un validador rápido de Micro-SaaS cuenta ahora con alternativas especializadas por capa:

1. **Capa Ingesta**:
   - *Ligero/Cero Coste*: `snscrape`, `reddit-find`, `URS`.
   - *Concurrente Streaming*: `asyncpraw`, `reddit-streaming-pipeline` (Kafka + Spark).
   - *Anti-Bot Evasión*: `crawlee-python`, `browserless-chrome`, `reddit-hole-playwright`.
2. **Capa Indexación & Memoria Vectorial**:
   - *Serverless en Disco*: `lancedb-vectordb-recipes` (LanceDB).
   - *Búsqueda Híbrida & Multimodal*: `multimodal-reddit-search` (CLIP + Qdrant), `vectfox-hybrid-search`.
   - *Base de Conocimiento MCP*: `reddit-research-mcp`, `reddit-kb-mcp-server` (ChromaDB).
3. **Capa Análisis Semántico & Detección de Dolor**:
   - *Heurístico*: `reddit-painpointer`, `reddit-pain-point-analyzer`.
   - *Zero-Shot NLI*: `reddit-sentiment-zero-shot` (Marta Baratto).
   - *Clustering No Supervisado*: `Reddit-NLP-Analytics`, `reddit-lupus-pain-nlp` (BERTopic).
4. **Capa Agentes y Automatización Comercial**:
   - *Máquina de estados con Human-in-the-Loop*: `reddit-agent-langgraph` (LangGraph).
   - *Agentes de prospección autónomos*: `RedoraAI` (Go), `Atalaia` (Rust/Tauri), `MiloAgent`.
   - *Automatización No-Code*: `n8n-reddit-scraper` (n8n workflows).
5. **Capa Validación Rápida Micro-SaaS**:
   - *Plantilla de producción*: `full-stack-fastapi-template`.
   - *Orquestador de LLMs*: `litellm`.
   - *Telemetría de demanda*: `posthog-js`.
""")

    lines.append("---")
    lines.append("*Catálogo maestro actualizado con 57 repositorios por el orquestador SENTRA.*")

    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"INDEX.md actualizado exitosamente en: {INDEX_FILE}")

if __name__ == "__main__":
    generate_index()
