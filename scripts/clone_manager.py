#!/usr/bin/env python3
"""
Orquestador de Descarga para Reddit Intelligence Radar
Clona superficialmente (--depth 1) los repositorios base y de expansion inteligente.
Maneja errores de red, repos privados o archivados con registro de incidencias.
"""

import json
import subprocess
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(r"F:\reddit_intelligence_radar")
REPOS_DIR = BASE_DIR / "repos"
LOGS_DIR = BASE_DIR / "logs"
RESULTS_FILE = LOGS_DIR / "clone_results.json"
ERRORS_FILE = LOGS_DIR / "errors.log"

REPOSITORIES = [
    # --- 1. Base Obligatoria Solicitada ---
    {
        "id": "praw",
        "owner": "praw-community",
        "repo": "praw",
        "category": "Extraction & API SDK",
        "tag": "Base",
        "reason": "SDK estándar de la industria para autenticación OAuth2, manejo de rate limits y streaming de Reddit."
    },
    {
        "id": "reddit-painpointer",
        "owner": "the-wc",
        "repo": "reddit-painpointer",
        "category": "Pain Point Mining",
        "tag": "Base",
        "reason": "Minería heurística y filtros léxicos de quejas para descubrimiento de problemas B2B."
    },
    {
        "id": "reddit-pain-point-analyzer",
        "owner": "thebarbariangroup",
        "repo": "reddit-pain-point-analyzer",
        "category": "Pain Point Mining",
        "tag": "Base",
        "reason": "Pipeline de procesamiento de quejas recurrentes enfocado en agencias y productos de consumo."
    },
    {
        "id": "saas-idea-finder",
        "owner": "Curt-Park",
        "repo": "saas-idea-finder",
        "category": "Demand & Micro-SaaS Validation",
        "tag": "Base",
        "reason": "Análisis cruzado de problemas en subreddits específicos frente a soluciones SaaS existentes."
    },
    {
        "id": "Atalaia",
        "owner": "mascanho",
        "repo": "Atalaia",
        "category": "Lead Generation & Social Listening",
        "tag": "Base",
        "reason": "Motor de monitoreo de palabras clave comerciales y captura de clientes potenciales en Reddit."
    },
    {
        "id": "Reddit-Product-Sentiment-Analytics",
        "owner": "Peris-Wallace",
        "repo": "Reddit-Product-Sentiment-Analytics",
        "category": "Sentiment & Intent Analysis",
        "tag": "Base",
        "reason": "Análisis de sentimiento orientado a productos con evaluación de percepciones de usuario."
    },
    {
        "id": "josephroi-reddit-scraper",
        "owner": "josephroi",
        "repo": "reddit-scraper",
        "category": "Extraction & Scrapers",
        "tag": "Base",
        "reason": "Scraper independiente para recolección de posts y comentarios sin dependencias masivas."
    },
    {
        "id": "pushshift-api",
        "owner": "pushshift",
        "repo": "api",
        "category": "Extraction & Ingestion Engines",
        "tag": "Base",
        "reason": "Arquitectura de backend para indexación y consulta a gran escala de datos históricos de Reddit."
    },
    {
        "id": "bulk-downloader-for-reddit",
        "owner": "aliparlakci",
        "repo": "bulk-downloader-for-reddit",
        "category": "Extraction & Ingestion Engines",
        "tag": "Base",
        "reason": "Descarga concurrente masiva, reintentos automáticos y preservación de jerarquías de contenido."
    },
    {
        "id": "bellingcat-reddit-scraper",
        "owner": "bellingcat",
        "repo": "reddit-scraper",
        "category": "Extraction & Scrapers",
        "tag": "Base",
        "reason": "Herramienta OSINT de alta confiabilidad para recolección rigurosa de metadatos y evidencia."
    },
    {
        "id": "pandas-ai",
        "owner": "gventuri",
        "repo": "pandas-ai",
        "category": "Data Transformation & LLM Analytics",
        "tag": "Base",
        "reason": "Capa conversacional sobre dataframes para consultar patrones de pain points en lenguaje natural."
    },
    {
        "id": "reddit-market-analyzer",
        "owner": "Firstbober",
        "repo": "reddit-market-analyzer",
        "category": "Demand & Micro-SaaS Validation",
        "tag": "Base",
        "reason": "Scoring de intención de compra y cuantificación de dolor para validación rápida de ideas."
    },
    {
        "id": "reddit-market-research",
        "owner": "neonwatty",
        "repo": "reddit-market-research",
        "category": "Demand & Micro-SaaS Validation",
        "tag": "Base",
        "reason": "Workflows de investigación de nichos y análisis competitivo en comunidades temáticas."
    },
    {
        "id": "pain-miner",
        "owner": "AdvancingTitans",
        "repo": "pain-miner",
        "category": "Pain Point Mining",
        "tag": "Base",
        "reason": "Minería semántica de dolor extrayendo oraciones de frustración de foros online."
    },
    {
        "id": "reddit-pain-points",
        "owner": "lefttree",
        "repo": "reddit-pain-points",
        "category": "Pain Point Mining",
        "tag": "Base",
        "reason": "Detección de problemas no resueltos mediante filtros semánticos y clustering."
    },
    {
        "id": "redditlens",
        "owner": "0xMassi",
        "repo": "redditlens",
        "category": "Sentiment & Intent Analysis",
        "tag": "Base",
        "reason": "Exploración visual y analítica de tendencias y opiniones en comunidades de Reddit."
    },
    {
        "id": "Scrapegraph-ai",
        "owner": "ScrapeGraphAI",
        "repo": "Scrapegraph-ai",
        "category": "Extraction & Ingestion Engines",
        "tag": "Base",
        "reason": "Extracción web basada en LLMs e inteligencia de grafos para scraping sin selectores rígidos."
    },
    {
        "id": "yt-dlp",
        "owner": "yt-dlp",
        "repo": "yt-dlp",
        "category": "Extraction Utilities & Media",
        "tag": "Base",
        "reason": "Arquitectura de referencia para extracción de medios, bypass de tokens de sesión y manejo de extractores."
    },
    {
        "id": "idea-box",
        "owner": "mothivenkatesh",
        "repo": "idea-box",
        "category": "Demand & Micro-SaaS Validation",
        "tag": "Base",
        "reason": "Catálogo estructurado de pain points para Vertical AI con análisis de TAM y WTP."
    },
    {
        "id": "FrictionLog",
        "owner": "Medalcode",
        "repo": "FrictionLog",
        "category": "Pain Point Mining",
        "tag": "Base",
        "reason": "Registro y clasificación de puntos de fricción técnica y de usabilidad reportados por usuarios."
    },
    {
        "id": "painpoint-atlas",
        "owner": "kelvinlee97",
        "repo": "painpoint-atlas",
        "category": "Pain Point Mining",
        "tag": "Base",
        "reason": "Taxonomía estructurada y mapa visual de áreas de dolor identificadas en discusiones públicas."
    },
    {
        "id": "reddit-pain-workflow",
        "owner": "minirr890112-byte",
        "repo": "reddit-pain-workflow",
        "category": "Pain Point Mining",
        "tag": "Base",
        "reason": "Pipelines automatizados de captura y scoring de quejas ciudadanas y de software."
    },
    {
        "id": "pain-to-pip-package",
        "owner": "minirr890112-byte",
        "repo": "pain-to-pip-package",
        "category": "Demand & Micro-SaaS Validation",
        "tag": "Base",
        "reason": "Transformación de problemas detectados en especificaciones de librerías y utilidades empaquetadas."
    },
    {
        "id": "litellm",
        "owner": "BerriAI",
        "repo": "litellm",
        "category": "LLM Routing & Gateway",
        "tag": "Base",
        "reason": "Proxy unificado y balanceo de carga para múltiples proveedores de LLM con manejo de costos y rate limits."
    },
    {
        "id": "browserless-chrome",
        "owner": "browserless",
        "repo": "chrome",
        "category": "Headless Crawling & Anti-Bot",
        "tag": "Base",
        "reason": "Infraestructura de headless browser en contenedor para scraping de páginas SPA y protección anti-bot."
    },
    {
        "id": "full-stack-fastapi-template",
        "owner": "tiangolo",
        "repo": "full-stack-fastapi-template",
        "category": "Micro-SaaS Architecture",
        "tag": "Base",
        "reason": "Arquitectura de referencia para micro-SaaS con FastAPI, PostgreSQL, autenticación JWT y frontend moderno."
    },
    {
        "id": "posthog-js",
        "owner": "PostHog",
        "repo": "posthog-js",
        "category": "Analytics & Validation Feedback",
        "tag": "Base",
        "reason": "Captura de eventos de usuario, heatmaps y telemetría de interacción para validación de landing pages."
    },
    {
        "id": "ArchiveBox",
        "owner": "ArchiveBox",
        "repo": "ArchiveBox",
        "category": "Data Preservation & Archiving",
        "tag": "Base",
        "reason": "Sistema autónomo de preservación web local para resguardar evidencia y volcados de posts eliminados."
    },

    # --- 2. Repositorios Adicionales de Social Listening, Monitoreo de Leads y Clustering ---
    {
        "id": "asyncpraw",
        "owner": "praw-community",
        "repo": "asyncpraw",
        "category": "Extraction & Concurrency",
        "tag": "Base Complement",
        "reason": "Implementación asíncrona de PRAW con asyncio para monitorear múltiples subreddits en tiempo real sin bloquear I/O."
    },
    {
        "id": "RedoraAI",
        "owner": "donebyai-team",
        "repo": "RedoraAI",
        "category": "Lead Generation & Outreach",
        "tag": "Expansion",
        "reason": "Plataforma de prospección en Reddit impulsada por IA con detección de subreddits relevantes y generación de mensajes context-aware."
    },
    {
        "id": "redsignal",
        "owner": "ivucicev",
        "repo": "redsignal",
        "category": "Lead Generation & Outreach",
        "tag": "Expansion",
        "reason": "Monitoreo en vivo de palabras clave, filtrado de ruido mediante LLMs locales/remotos y flujo de trabajo para respuestas rápidas."
    },
    {
        "id": "mohamedsaleh-reddit-scrapper",
        "owner": "Mohamedsaleh14",
        "repo": "Reddit_Scrapper",
        "category": "Pain Point Mining & UI",
        "tag": "Expansion",
        "reason": "Extracción focalizada de dolores de mercado conectada a modelos GPT con interfaz Streamlit para filtrado de oportunidades."
    },
    {
        "id": "business-ideas-dataset",
        "owner": "theomarsoliman",
        "repo": "business-ideas-dataset",
        "category": "Demand & Micro-SaaS Validation",
        "tag": "Expansion",
        "reason": "Dataset estructurado de ideas de negocio minadas de quejas reales con métricas de severidad, viabilidad y timing."
    },
    {
        "id": "reddit-nlp-analytics",
        "owner": "pranjal-pravesh",
        "repo": "Reddit-NLP-Analytics",
        "category": "Topic Modeling & Clustering",
        "tag": "Expansion",
        "reason": "Pipeline avanzado que une PRAW con BERTopic (clustering semántico con embeddings) y análisis de sentimiento RoBERTa."
    },
    {
        "id": "reddit-intelligence",
        "owner": "veluthoor",
        "repo": "Reddit-Intelligence",
        "category": "Market Intelligence",
        "tag": "Expansion",
        "reason": "Framework de agregación de inteligencia en Reddit para identificación sistemática de necesidades insatisfechas."
    },
    {
        "id": "reddit-intel-agent-mcp",
        "owner": "Houseofmvps",
        "repo": "reddit-intel-agent-mcp",
        "category": "MCP & Agentic Search",
        "tag": "Expansion",
        "reason": "Servidor MCP (Model Context Protocol) para búsqueda semántica, scoring de oportunidad y detección de intención de compra para agentes de IA."
    },
    {
        "id": "reddit-pain-research-skill",
        "owner": "haseebeqx",
        "repo": "reddit-pain-research-skill",
        "category": "Agent Skills & Research",
        "tag": "Expansion",
        "reason": "Skill modular de agente para planificar estudios de mercado en Reddit, agrupar evidencia y formular hipótesis de monetización."
    },
    {
        "id": "social-listening-tool",
        "owner": "phil-morton",
        "repo": "social-listening-tool",
        "category": "Lead Generation & Social Listening",
        "tag": "Expansion",
        "reason": "Herramienta ligera de social listening orientada a streaming de discusiones en formato JSONL para pipelines downstream."
    },
    {
        "id": "milo-agent",
        "owner": "SoCloseSociety",
        "repo": "MiloAgent",
        "category": "Autonomous Lead Agents",
        "tag": "Expansion",
        "reason": "Agente autónomo de crecimiento para Reddit y redes sociales que automatiza el descubrimiento de conversaciones relevantes."
    },
    {
        "id": "snscrape",
        "owner": "JustAnotherArchivist",
        "repo": "snscrape",
        "category": "Extraction & Scrapers",
        "tag": "Expansion",
        "reason": "Scraper altamente optimizado sin autenticación para redes sociales, capaz de extraer posts históricos de Reddit sin API keys."
    },
    {
        "id": "crawlee-python",
        "owner": "apify",
        "repo": "crawlee-python",
        "category": "Headless Crawling & Anti-Bot",
        "tag": "Expansion",
        "reason": "Framework de crawling de última generación con rotación de sesiones, fingerprints de navegador y evasión de bloqueos."
    },
    {
        "id": "awesome-ai-lead-generation",
        "owner": "toofast1",
        "repo": "awesome-ai-lead-generation",
        "category": "Knowledge Base & Strategy",
        "tag": "Expansion",
        "reason": "Compendio de arquitecturas y estrategias para generación de leads B2B mediante social listening e intención de compra."
    },
    {
        "id": "awesome-reddit-lead-gen",
        "owner": "jeeiee",
        "repo": "awesome-reddit-lead-gen",
        "category": "Knowledge Base & Strategy",
        "tag": "Expansion",
        "reason": "Directorio especializado de técnicas, scripts y flujos probados para prospección comercial ética en Reddit."
    },
    {
        "id": "reddit-lupus-pain-nlp",
        "owner": "bozlab",
        "repo": "reddit-lupus-pain-nlp",
        "category": "Topic Modeling & Clustering",
        "tag": "Expansion",
        "reason": "Implementación rigurosa de BERTopic para extracción temática de dolor y análisis léxico comparativo en comunidades de salud."
    },
    {
        "id": "reddit-archive-core",
        "owner": "reddit-archive",
        "repo": "reddit",
        "category": "Internal Architecture & Data Model",
        "tag": "Expansion",
        "reason": "Código fuente original del backend de Reddit (Thing, Account, Subreddit, Comment trees) fundamental para entender cómo Reddit estructura y clasifica la data."
    }
]

def run_clone():
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    if RESULTS_FILE.exists():
        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                results = json.load(f)
        except (OSError, json.JSONDecodeError):
            results = []

    already_processed = {r["id"]: r for r in results if r.get("status") in ["success", "already_present"]}

    print("=== INICIANDO ORQUESTADOR DE CLONACION ===")
    print(f"Total de repositorios catalogados: {len(REPOSITORIES)}")
    print(f"Directorio de destino: {REPOS_DIR}")
    print("=" * 50)

    for i, item in enumerate(REPOSITORIES, 1):
        repo_id = item["id"]
        owner = item["owner"]
        repo = item["repo"]
        target_folder = REPOS_DIR / repo_id
        url = f"https://github.com/{owner}/{repo}.git"

        print(f"\n[{i}/{len(REPOSITORIES)}] Procesando {owner}/{repo} -> {repo_id}...")

        # Verificar si ya fue clonado exitosamente
        if target_folder.exists() and (target_folder / ".git").exists():
            print(f"  [OK] El repositorio ya existe en {target_folder}. Omitiendo descarga.")
            status_entry: dict[str, Any] = {
                "id": repo_id,
                "owner": owner,
                "repo": repo,
                "url": url,
                "category": item["category"],
                "tag": item["tag"],
                "reason": item["reason"],
                "folder": str(target_folder),
                "status": "success",
                "message": "Already present on disk",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            # Actualizar o agregar
            already_processed[repo_id] = status_entry
            continue

        start_time = time.time()
        cmd = ["git", "clone", "--depth", "1", url, str(target_folder)]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,  # 2 minutos maximo por repositorio
                check=False,  # el código de salida se trata abajo
            )

            duration = round(time.time() - start_time, 2)

            if proc.returncode == 0:
                print(f"  [EXITO] Clonado en {duration}s -> {target_folder.name}")
                status_entry = {
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
                    "message": "Cloned successfully",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }
            else:
                err_msg = proc.stderr.strip()
                print(f"  [FALLO] Codigo {proc.returncode}: {err_msg[:120]}")
                # Loggear a errors.log
                with open(ERRORS_FILE, "a", encoding="utf-8") as ef:
                    ef.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR al clonar {url}:\n{err_msg}\n{'-'*40}\n")
                
                status_entry = {
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
                    "error": err_msg,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }

        except subprocess.TimeoutExpired:
            duration = round(time.time() - start_time, 2)
            print("  [TIMEOUT] Excedio el tiempo limite de 120s.")
            with open(ERRORS_FILE, "a", encoding="utf-8") as ef:
                ef.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] TIMEOUT al clonar {url} tras {duration}s\n{'-'*40}\n")
            status_entry = {
                "id": repo_id,
                "owner": owner,
                "repo": repo,
                "url": url,
                "category": item["category"],
                "tag": item["tag"],
                "reason": item["reason"],
                "folder": str(target_folder),
                "status": "timeout",
                "duration_seconds": duration,
                "error": "Git clone timed out after 120s",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }

        except (OSError, subprocess.SubprocessError) as e:
            duration = round(time.time() - start_time, 2)
            print(f"  [EXCEPCION] {e!s}")
            with open(ERRORS_FILE, "a", encoding="utf-8") as ef:
                ef.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] EXCEPCION con {url}: {e!s}\n{'-'*40}\n")
            status_entry = {
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

        already_processed[repo_id] = status_entry

        # Guardar progreso incremental
        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(already_processed.values()), f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 50)
    print("RESUMEN DE CLONACION:")
    total = len(already_processed)
    success = sum(1 for r in already_processed.values() if r["status"] == "success")
    failed = sum(1 for r in already_processed.values() if r["status"] != "success")
    print(f"Procesados: {total} | Exitosos: {success} | Fallidos/Omitidos: {failed}")
    print(f"Registro guardado en: {RESULTS_FILE}")
    if failed > 0:
        print(f"Detalle de errores en: {ERRORS_FILE}")
    print("=" * 50)

if __name__ == "__main__":
    run_clone()
