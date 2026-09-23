#!/usr/bin/env python3
"""
Orquestador de Descarga - Lote 2 para Reddit Intelligence Radar
Clona la nueva tanda de repositorios diferenciales enfocados en:
- LangGraph multi-agentes
- n8n visual workflows
- Kafka/Spark big data streaming
- LanceDB / Qdrant vector databases & multimodal CLIP
- Zero-shot classification
- Playwright browser automation
"""

import json
import subprocess
import time
from pathlib import Path

BASE_DIR = Path(r"F:\reddit_intelligence_radar")
REPOS_DIR = BASE_DIR / "repos"
LOGS_DIR = BASE_DIR / "logs"
RESULTS_FILE = LOGS_DIR / "clone_results.json"
ERRORS_FILE = LOGS_DIR / "errors.log"

NEW_REPOSITORIES = [
    {
        "id": "reddit-find",
        "owner": "LeadGrowGTM",
        "repo": "reddit-find",
        "category": "GTM & Buyer Language Extraction",
        "tag": "Batch 2",
        "reason": "Herramienta de investigación GTM que extrae lenguaje del comprador, puntos de dolor y ángulos de contenido de Reddit sin requerir API key, exportando markdown estructurado para LLMs.",
        "preferred_files": ["find.py", "reddit.py", "main.py", "README.md"]
    },
    {
        "id": "reddit-agent-langgraph",
        "owner": "avisangle",
        "repo": "reddit_agent",
        "category": "LangGraph Autonomous Agents",
        "tag": "Batch 2",
        "reason": "Agente de engagement en Reddit 'compliance-first' implementado con LangGraph: máquina de estados, scoring de calidad con IA, aprobación humana interactiva (Slack/Telegram) y publicación controlada.",
        "preferred_files": ["agent.py", "graph.py", "reddit_client.py", "main.py"]
    },
    {
        "id": "reddit-research-mcp",
        "owner": "dialog-tools",
        "repo": "reddit-research-mcp",
        "category": "MCP & Semantic Discovery",
        "tag": "Batch 2",
        "reason": "Servidor MCP (Model Context Protocol) para asistentes de IA (Claude/Cursor/Gemini) que realiza búsqueda semántica profunda y citaciones verificadas sobre más de 20,000 subreddits.",
        "preferred_files": ["src/index.ts", "src/server.ts", "package.json", "README.md"]
    },
    {
        "id": "n8n-reddit-scraper",
        "owner": "gguyon0925",
        "repo": "n8n-reddit-scraper",
        "category": "Visual Workflows & Automation",
        "tag": "Batch 2",
        "reason": "Plantillas de automatización listas para importar en n8n enfocadas en prospección de leads con intención de compra, investigación de audiencias e integración de agentes IA mediante MCP.",
        "preferred_files": ["workflows/", "README.md"]
    },
    {
        "id": "reddit-streaming-pipeline",
        "owner": "nama1arpit",
        "repo": "reddit-streaming-pipeline",
        "category": "Big Data Streaming & Distributed Processing",
        "tag": "Batch 2",
        "reason": "Pipeline distribuido en tiempo real para comentarios de Reddit utilizando Apache Kafka para streaming, Apache Spark para procesamiento distribuido, Cassandra para almacenamiento y Grafana para visualización.",
        "preferred_files": ["spark_streaming.py", "kafka_producer.py", "docker-compose.yml", "README.md"]
    },
    {
        "id": "reddit-sentiment-analysis-fullstack",
        "owner": "netto14cr",
        "repo": "reddit_sentiment_analysis",
        "category": "Full-Stack Sentiment Platforms",
        "tag": "Batch 2",
        "reason": "Plataforma full-stack con backend Flask y frontend React para clasificar el sentimiento de publicaciones en Reddit mediante modelos de Machine Learning y visualización de métricas comunitarias.",
        "preferred_files": ["backend/app.py", "backend/model.py", "frontend/src/App.js", "README.md"]
    },
    {
        "id": "reddit-kb-mcp-server",
        "owner": "lh1207",
        "repo": "reddit-kb-mcp-server",
        "category": "ChromaDB & Knowledge Management",
        "tag": "Batch 2",
        "reason": "Servidor MCP que indexa contenido de Reddit en la base de datos vectorial ChromaDB generando embeddings para permitir recuperación semántica personalizada.",
        "preferred_files": ["server.py", "chroma_client.py", "requirements.txt", "README.md"]
    },
    {
        "id": "multimodal-reddit-search",
        "owner": "DaveOkpare",
        "repo": "multimodal-search",
        "category": "Qdrant & Multimodal Search",
        "tag": "Batch 2",
        "reason": "Motor de búsqueda multimodal que ingesta posts de Reddit, genera embeddings conjuntos de texto e imágenes mediante OpenAI CLIP y los almacena en Qdrant para similitud vectorial.",
        "preferred_files": ["search.py", "ingest.py", "app.py", "README.md"]
    },
    {
        "id": "reddit-sentiment-zero-shot",
        "owner": "marta-baratto",
        "repo": "Reddit_sentiment",
        "category": "Zero-Shot NLP Classification",
        "tag": "Batch 2",
        "reason": "Pipeline de investigación para modelar la propagación de sentimiento en comunidades de Reddit mediante clasificación zero-shot basada en NLI (Natural Language Inference) sin necesidad de datos de entrenamiento previos.",
        "preferred_files": ["sentiment_analysis.py", "zero_shot.py", "preprocess.py", "README.md"]
    },
    {
        "id": "reddit-hole-playwright",
        "owner": "nssharmaofficial",
        "repo": "reddit-hole",
        "category": "Playwright Browser Automation",
        "tag": "Batch 2",
        "reason": "Crawler automatizado de Reddit basado en Playwright para evasión de bloqueos dinámicos en JavaScript, renderizado de DOM interactivo y extracción estructurada de hilos.",
        "preferred_files": ["scraper.py", "crawler.py", "main.py", "package.json"]
    },
    {
        "id": "lancedb-vectordb-recipes",
        "owner": "lancedb",
        "repo": "vectordb-recipes",
        "category": "LanceDB Serverless Vectors",
        "tag": "Batch 2",
        "reason": "Repositorio oficial de arquitecturas de referencia para LanceDB: bases de datos vectoriales serverless en disco con consultas de baja latencia y RAG sobre comentarios y posts de Reddit.",
        "preferred_files": ["examples/", "tutorials/", "README.md"]
    },
    {
        "id": "vectfox-hybrid-search",
        "owner": "KritBlade",
        "repo": "VectFox",
        "category": "Qdrant Hybrid Search & Memory",
        "tag": "Batch 2",
        "reason": "Sistema de memoria y búsqueda híbrida (dense embeddings + sparse lexical) implementado sobre Qdrant para summarization y recuperación de contexto conversacional en foros.",
        "preferred_files": ["src/", "vectfox/", "main.py", "README.md"]
    }
]

def run_clone_batch2():
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        existing_results = json.load(f)

    existing_ids = {r["id"] for r in existing_results}
    results_map = {r["id"]: r for r in existing_results}

    print("=== INICIANDO CLONACION DE LOTE 2 (EXPANSION DIFERENCIAL) ===")
    print(f"Total de nuevos candidatos: {len(NEW_REPOSITORIES)}")
    print("=" * 50)

    for i, item in enumerate(NEW_REPOSITORIES, 1):
        repo_id = item["id"]
        owner = item["owner"]
        repo = item["repo"]
        target_folder = REPOS_DIR / repo_id
        url = f"https://github.com/{owner}/{repo}.git"

        if repo_id in existing_ids and target_folder.exists() and (target_folder / ".git").exists():
            print(f"[{i}/{len(NEW_REPOSITORIES)}] Omitiendo {repo_id} (ya presente en disco).")
            continue

        print(f"\n[{i}/{len(NEW_REPOSITORIES)}] Clonando {owner}/{repo} -> {repo_id}...")
        start_time = time.time()
        cmd = ["git", "clone", "--depth", "1", url, str(target_folder)]

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            duration = round(time.time() - start_time, 2)

            if proc.returncode == 0:
                print(f"  [EXITO] Clonado en {duration}s -> {target_folder.name}")
                entry = {
                    "id": repo_id,
                    "owner": owner,
                    "repo": repo,
                    "url": url,
                    "category": item["category"],
                    "tag": item["tag"],
                    "reason": item["reason"],
                    "folder": str(target_folder),
                    "status": "success",
                    "duration_seconds": duration,
                    "message": "Cloned successfully (Batch 2)",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }
            else:
                err = proc.stderr.strip()
                print(f"  [FALLO] Codigo {proc.returncode}: {err[:120]}")
                with open(ERRORS_FILE, "a", encoding="utf-8") as ef:
                    ef.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR Batch 2 {url}:\n{err}\n{'-'*40}\n")
                entry = {
                    "id": repo_id,
                    "owner": owner,
                    "repo": repo,
                    "url": url,
                    "category": item["category"],
                    "tag": item["tag"],
                    "reason": item["reason"],
                    "folder": str(target_folder),
                    "status": "failed",
                    "duration_seconds": duration,
                    "error": err,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }
        except Exception as e:
            duration = round(time.time() - start_time, 2)
            print(f"  [EXCEPCION] {e!s}")
            with open(ERRORS_FILE, "a", encoding="utf-8") as ef:
                ef.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] EXCEPCION Batch 2 {url}: {e!s}\n{'-'*40}\n")
            entry = {
                "id": repo_id,
                "owner": owner,
                "repo": repo,
                "url": url,
                "category": item["category"],
                "tag": item["tag"],
                "reason": item["reason"],
                "folder": str(target_folder),
                "status": "error",
                "duration_seconds": duration,
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }

        results_map[repo_id] = entry
        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(results_map.values()), f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 50)
    print("RESUMEN LOTE 2:")
    new_success = sum(1 for item in NEW_REPOSITORIES if results_map.get(item["id"], {}).get("status") == "success")
    print(f"Total lote 2 intentados: {len(NEW_REPOSITORIES)} | Exitosos: {new_success}")
    print(f"Total acumulado en radar: {len(results_map)}")
    print("=" * 50)

if __name__ == "__main__":
    run_clone_batch2()
