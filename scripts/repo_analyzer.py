#!/usr/bin/env python3
"""
Analizador Estatico y Extractor de Modulos Clave para Reddit Intelligence Radar
Inspecciona con precision los repositorios descargados en F:\\reddit_intelligence_radar\\repos\\,
detecta los archivos de logica de negocio real mediante heuristica de scoring
y extrae las rutas relativas exactas para ingenieria inversa.
"""

import json
from pathlib import Path

BASE_DIR = Path(r"F:\reddit_intelligence_radar")
REPOS_DIR = BASE_DIR / "repos"
LOGS_DIR = BASE_DIR / "logs"
RESULTS_FILE = LOGS_DIR / "clone_results.json"
CATALOG_FILE = LOGS_DIR / "repo_catalog.json"

REPO_METADATA = {
    "praw": {
        "title": "PRAW (Python Reddit API Wrapper)",
        "differential": "SDK oficial y estándar industrial en Python: autenticación OAuth2 transparente, auto-throttling según rate limits oficiales de Reddit (60 req/min) y streams perezosos de posts y comentarios.",
        "preferred_files": ["praw/reddit.py", "praw/models/listing/mixins/subreddit.py", "praw/models/reddit/subreddit.py", "praw/models/reddit/comment.py"]
    },
    "asyncpraw": {
        "title": "Async PRAW",
        "differential": "Implementación asíncrona de alto rendimiento construida sobre aiohttp y asyncio, diseñada para consumir streams de múltiples subreddits concurrentes sin bloquear el hilo principal.",
        "preferred_files": ["asyncpraw/reddit.py", "asyncpraw/models/reddit/subreddit.py", "asyncpraw/models/reddit/submission.py", "asyncpraw/models/auth.py"]
    },
    "reddit-painpointer": {
        "title": "reddit-painpointer",
        "differential": "Filtro léxico y heurístico de quejas recurrentes ('I hate when', 'Is there any tool', 'struggling with') con extracción y clasificación de dolor B2B sobre comunidades de nicho.",
        "preferred_files": ["app/lib/reddit.ts", "app/routes/subreddit.tsx", "app/root.tsx", "package.json"]
    },
    "reddit-pain-point-analyzer": {
        "title": "reddit-pain-point-analyzer",
        "differential": "Pipeline de análisis de quejas de usuarios con métricas de severidad y frecuencia para agencias de investigación de mercado y lanzamientos de producto.",
        "preferred_files": ["reddit_analyzer.py", "app.py", "templates/index.html", "requirements.txt"]
    },
    "saas-idea-finder": {
        "title": "saas-idea-finder",
        "differential": "Arquitectura multi-agente para correspondencia problema-solución: mapea comunidades, detecta peticiones de producto insatisfechas y sugiere características MVP diferenciadoras.",
        "preferred_files": ["src/agents/problem_analyzer.py", "src/agents/competitive_landscape_analyzer.py", "src/agents/mvp_feature_suggester.py", "main.py"]
    },
    "Atalaia": {
        "title": "Atalaia (Desktop Lead Listener)",
        "differential": "Plataforma de escritorio (Next.js + Tauri + Rust) para social listening y generación de leads: monitoriza intenciones de compra en Reddit y ejecuta análisis contextual con Google Gemini.",
        "preferred_files": ["src-tauri/src/ai/gemini.rs", "src/components/leads-generator.tsx", "src/components/reddit-search/index.ts", "src-tauri/src/models/search.rs"]
    },
    "Reddit-Product-Sentiment-Analytics": {
        "title": "Reddit-Product-Sentiment-Analytics",
        "differential": "Matriz de sentimiento granular por facetas de producto (precio, UX, estabilidad, servicio al cliente) utilizando modelos de NLP sobre hilos técnicos.",
        "preferred_files": ["scraper.py", "src/sample_scraper_with_search_terms.py", "src/sample_top_posts_scraper.py"]
    },
    "urs-reddit-scraper": {
        "title": "Universal Reddit Scraper (URS)",
        "differential": "CLI de scraping forense exhaustivo sin overhead, con soporte para recolección de comentarios anidados multinivel, feeds en vivo (Livestream) y perfiles en JSON/CSV.",
        "preferred_files": ["urs/praw_scrapers/live_scrapers/Livestream.py", "urs/Urs.py", "urs/utils/DirInit.py", "urs/praw_scrapers/Subreddit.py"]
    },
    "pushshift-api": {
        "title": "Pushshift API Core",
        "differential": "Arquitectura de backend para indexación y consulta a escala de petabytes de publicaciones y comentarios históricos de Reddit mediante Elasticsearch y PostgreSQL.",
        "preferred_files": ["api/api.py", "api/Comment.py", "api/DBFunctions.py", "api/Subreddit.py"]
    },
    "bulk-downloader-for-reddit": {
        "title": "Bulk Downloader for Reddit (BDFR)",
        "differential": "Descargador concurrente con multithreading resiliente, resolución automatizada de URLs CDN (v.redd.it, imgur, gfycat) y deduplicación basada en hashing de contenido.",
        "preferred_files": ["bdfr/site_downloaders/delay_for_reddit.py", "bdfr/site_downloaders/vreddit.py", "bdfr/downloader.py", "bdfr/cli.py"]
    },
    "bellingcat-reddit-post-scraping-tool": {
        "title": "Bellingcat Reddit Post Scraping Tool",
        "differential": "Metodología OSINT forense para búsqueda de evidencia por palabras clave en Reddit con preservación estricta de marcas de tiempo UTC, IDs y metadatos de autor.",
        "preferred_files": ["rpst/scraper.py", "rpst/api.py", "rpst/base.py", "main.py"]
    },
    "pandas-ai": {
        "title": "PandasAI",
        "differential": "Agente RAG tabular conversacional: transforma lenguaje natural en código Pandas ejecutable y consultas estadísticas, ideal para interrogar datasets de quejas de Reddit.",
        "preferred_files": ["pandasai/agent/base.py", "pandasai/agent/state.py", "pandasai/smart_dataframe/", "pandasai/pipelines/"]
    },
    "reddit-market-analyzer": {
        "title": "reddit-market-analyzer",
        "differential": "Scoring algorítmico de intención de compra (Buying Intent Index) y detección de debilidades de la competencia para validar demanda comercial de micro-SaaS.",
        "preferred_files": ["market_analyzer.py", "src/analysis/llm_client.py", "src/product_ideas/ideator.py", "src/scraper/reddit_scraper.py"]
    },
    "reddit-market-research": {
        "title": "reddit-market-research",
        "differential": "Monitoreo continuo de nichos de mercado en Reddit con categorización automática de publicaciones por relevancia comercial y engagement.",
        "preferred_files": ["reddit_monitor.py", "tests/test_reddit_monitor.py", "pyproject.toml"]
    },
    "pain-miner": {
        "title": "pain-miner",
        "differential": "Minería semántica de dolor extrayendo oraciones de frustración de usuarios mediante modelos de clasificación de texto y generación de informes de oportunidad.",
        "preferred_files": ["painminer/analysis.py", "painminer/models.py", "painminer/report.py", "painminer/cli.py"]
    },
    "reddit-pain-points": {
        "title": "reddit-pain-points",
        "differential": "Scraper y analizador dual (público y autenticado) para agrupar quejas de clientes y categorizar puntos de dolor sin resolver.",
        "preferred_files": ["backend/scraper.py", "backend/scraper_public.py", "backend/cli.py", "backend/models.py"]
    },
    "redditlens": {
        "title": "RedditLens",
        "differential": "Herramienta analítica visual construida en TypeScript para explorar el pulso y sentimiento de comunidades en Reddit mediante interacción directa con la API.",
        "preferred_files": ["src/reddit.ts", "src/cli.ts", "src/http.ts", "package.json"]
    },
    "Scrapegraph-ai": {
        "title": "ScrapeGraphAI",
        "differential": "Extracción web basada en grafos de razonamiento con LLMs: sintetiza esquemas de datos estructurados de foros y páginas web sin depender de selectores CSS rígidos.",
        "preferred_files": ["scrapegraphai/graphs/smart_scraper_graph.py", "scrapegraphai/nodes/fetch_html_node.py", "scrapegraphai/nodes/parse_node.py"]
    },
    "yt-dlp": {
        "title": "yt-dlp",
        "differential": "Extractor de medios de Reddit (`extractor/reddit.py`): arquitectura de bypass de tokens de sesión, reconstrucción de streams DASH/HLS de audio/video y evasión de bloqueos.",
        "preferred_files": ["yt_dlp/extractor/reddit.py", "yt_dlp/extractor/common.py", "yt_dlp/downloader/common.py"]
    },
    "idea-box": {
        "title": "idea-box",
        "differential": "Dataset estructurado de 1000 pain points validados para Vertical AI con análisis de Persona, TAM y Willingness-To-Pay (WTP), con utilidades de ingesta.",
        "preferred_files": ["scripts/add-pain.py", "data/pains-01-repair-home-services.json", "data/pains-02-marketing-gtm-revops.json", "README.md"]
    },
    "FrictionLog": {
        "title": "FrictionLog",
        "differential": "Framework estructurado para registrar y categorizar fricciones técnicas, bloqueos de adopción y experiencias negativas detectadas en retroalimentación de usuarios.",
        "preferred_files": ["llm_client.py", "AGENTS.md", "docs/agents.md"]
    },
    "painpoint-atlas": {
        "title": "painpoint-atlas (Opportunity Radar)",
        "differential": "Radar de oportunidades de negocio con modelos de datos para cuantificar la intensidad de problemas y scripts de orquestación de mercado.",
        "preferred_files": ["opportunity_radar/models.py", "opportunity_radar/cli.py", "tests/test_workflow_security.py"]
    },
    "reddit-pain-workflow": {
        "title": "reddit-pain-workflow",
        "differential": "Pipeline CLI de extracción y síntesis automatizada de dolor en Reddit, diseñado para integrarse con herramientas de automatización CI/CD.",
        "preferred_files": ["reddit_pain/cli.py", "reddit_pain_workflow.py", "reddit_pain/__init__.py"]
    },
    "pain-to-pip-package": {
        "title": "pain-to-pip-package",
        "differential": "Metodología automatizada de conversión de dolores de desarrollo extraídos en Reddit hacia la generación de especificaciones de librerías Python instalables.",
        "preferred_files": ["pain_to_pip/cli.py", "pipeline.py", "pain_to_pip/__init__.py"]
    },
    "litellm": {
        "title": "LiteLLM",
        "differential": "Capa gateway universal de LLMs: gestiona conmutación por error (fallbacks), balanceo de carga, control estricto de presupuestos de tokens y caché para pipelines de scraping masivo.",
        "preferred_files": ["litellm/router.py", "litellm/main.py", "litellm/proxy/proxy_server.py"]
    },
    "browserless-chrome": {
        "title": "browserless/chrome",
        "differential": "Infraestructura de headless Chrome en contenedores con API REST para scraping de SPAs, evasión de desafíos Cloudflare y captura de DOM completo de Reddit.",
        "preferred_files": ["src/shared/scrape.http.ts", "src/routes/chrome/http/scrape.post.ts", "Dockerfile", "package.json"]
    },
    "full-stack-fastapi-template": {
        "title": "Full Stack FastAPI Template",
        "differential": "Arquitectura de producción lista para lanzar micro-SaaS: backend FastAPI asíncrono, autenticación JWT, modelos SQLModel/PostgreSQL y frontend React.",
        "preferred_files": ["backend/app/models.py", "backend/app/api/main.py", "backend/app/core/db.py", "frontend/src/client/index.ts"]
    },
    "posthog-js": {
        "title": "posthog-js",
        "differential": "SDK de instrumentación para validación de demanda: seguimiento de conversión en botones de lista de espera ('Join Waitlist'), mapas de calor y analítica de retención.",
        "preferred_files": ["packages/ai/src/claude-agent-sdk/index.ts", "packages/ai/src/openai-agents/index.ts", "src/posthog-core.ts"]
    },
    "ArchiveBox": {
        "title": "ArchiveBox",
        "differential": "Plataforma de preservación web autoalojada con servidor MCP integrado, captura de texto completo e indexación de páginas para resguardar evidencia eliminada.",
        "preferred_files": ["archivebox/mcp/server.py", "archivebox/extractors/singlefile.py", "archivebox/core/models.py"]
    },
    "RedoraAI": {
        "title": "RedoraAI",
        "differential": "Plataforma de prospección automatizada en Reddit impulsada por agentes autónomos en Go y clientes web en TypeScript para detección de leads e interacciones no invasivas.",
        "preferred_files": ["backend/agents/agents.go", "backend/agents/agents_enum.go", "frontend/packages/client/index.ts"]
    },
    "redsignal": {
        "title": "redsignal",
        "differential": "Monitor de Reddit con filtrado de ruido por IA (compatible con Ollama y OpenAI) y panel de control web para calificar y responder oportunidades comerciales.",
        "preferred_files": ["app.py", "frontend/index.html", "static/index.html"]
    },
    "mohamedsaleh-reddit-scrapper": {
        "title": "Reddit_Scrapper (Mohamed Saleh)",
        "differential": "Extractor de problemas de mercado con módulo de control de tasa (`rate_limiter.py`), descubrimiento de subreddits y análisis de dolor vía modelos GPT.",
        "preferred_files": ["reddit/rate_limiter.py", "reddit/discovery.py", "reddit/scraper.py", "app.py"]
    },
    "business-ideas-dataset": {
        "title": "Business Ideas Dataset",
        "differential": "Catálogo estructurado de ideas de negocio y oportunidades B2B minadas directamente de Reddit y reviews públicas, con scoring de viabilidad y severidad de problema.",
        "preferred_files": ["data/ideas.csv", "data/ideas.json", "examples/app-ideas.md", "README.md"]
    },
    "reddit-nlp-analytics": {
        "title": "Reddit NLP Analytics",
        "differential": "Pipeline de NLP completo que une la ingesta de Reddit con modelado de tópicos BERTopic (c-TF-IDF + embeddings) y análisis de sentimiento con modelos RoBERTa.",
        "preferred_files": ["app/services/nlp_service.py", "app/services/reddit_client.py", "app/api/v1/endpoints/reddit.py"]
    },
    "reddit-intelligence": {
        "title": "Reddit-Intelligence",
        "differential": "Suite de agregación de inteligencia competitiva con backend FastAPI y servicios especializados de scraping (`scraper_service.py`) para monitorear feedback.",
        "preferred_files": ["backend/app/scraper_service.py", "backend/app/models.py", "backend/app/main.py"]
    },
    "reddit-intel-agent-mcp": {
        "title": "BuildRadar Reddit Intel Agent MCP",
        "differential": "Servidor MCP (Model Context Protocol) para asistentes de IA que expone herramientas de scoring de oportunidad, tracking de competidores y prospección de leads en Reddit.",
        "preferred_files": ["src/intelligence/subreddit-analyzer.ts", "src/api/reddit-oauth.ts", "src/reddit/client.ts", "src/index.ts"]
    },
    "reddit-pain-research-skill": {
        "title": "Reddit Pain Research Skill",
        "differential": "Skill modular de agente de IA para planificar estudios de mercado en comunidades de Reddit, agrupar evidencia empírica y generar hipótesis de monetización.",
        "preferred_files": ["reddit-pain-research/SKILL.md", "reddit-pain-research/scripts/build_reports.py", "reddit-pain-research/scripts/create_research_config.py"]
    },
    "social-listening-tool": {
        "title": "Social Listening Tool",
        "differential": "Script ligero de captura continua de menciones en Reddit (`reddit-pull.py`) con exportación estructurada a JSONL para procesamiento analítico en downstream.",
        "preferred_files": ["reddit-pull.py", "README.md"]
    },
    "milo-agent": {
        "title": "MiloAgent",
        "differential": "Agente autónomo de crecimiento multi-comunidad con motor de investigación (`research_engine.py`) y hub de gestión de subreddits (`subreddit_hub.py`).",
        "preferred_files": ["miloagent.py", "core/research_engine.py", "core/subreddit_hub.py"]
    },
    "snscrape": {
        "title": "snscrape",
        "differential": "Extracción sin autenticación vía protocolo público de Reddit (`snscrape/modules/reddit.py`), prescindiendo de credenciales y evitando bloqueos de API.",
        "preferred_files": ["snscrape/modules/reddit.py", "snscrape/_cli.py", "snscrape/base.py"]
    },
    "crawlee-python": {
        "title": "Crawlee for Python",
        "differential": "Framework de crawling profesional con soporte para Playwright, rotación inteligente de proxies, emulación de huella TLS/HTTP2 (`curl-impersonate`) y colas de URLs.",
        "preferred_files": ["docs/guides/code_examples/http_clients/parsel_curl_impersonate_example.py", "src/crawlee/crawlers/", "src/crawlee/sessions/"]
    },
    "awesome-ai-lead-generation": {
        "title": "Awesome AI Lead Generation",
        "differential": "Directorio exhaustivo de herramientas, frameworks y arquitecturas probadas para generación de leads e identificación de intención comercial con IA.",
        "preferred_files": ["README.md", "CONTRIBUTING.md"]
    },
    "awesome-reddit-lead-gen": {
        "title": "Awesome Reddit Lead Gen",
        "differential": "Guía táctica de prospección comercial en Reddit: mapeo de subreddits de alto valor, plantillas de búsqueda booleana y reglas anti-baneo de la comunidad.",
        "preferred_files": ["README.md"]
    },
    "reddit-lupus-pain-nlp": {
        "title": "Reddit Lupus Pain NLP",
        "differential": "Implementación práctica de modelado de tópicos con BERTopic aplicada a la extracción de quejas y dolor en hilos de salud, con vocabulario léxico curado.",
        "preferred_files": ["pain_vocabulary_lupus_reddit.xlsx", "one-sentence/1 - single_sentence_topic_modeling.ipynb", "Topic modeling details.docx"]
    },
    "reddit-archive-core": {
        "title": "Reddit Core (Historical Monolith)",
        "differential": "Código fuente original del backend de Reddit: controladores base, modelos de Thing/Account/Comment y algoritmos de búsqueda y ranking de subreddits.",
        "preferred_files": ["r2/r2/controllers/reddit_base.py", "r2/r2/lib/subreddit_search.py", "r2/r2/models/comment.py"]
    },
    "reddit-find": {
        "title": "reddit-find (GTM Buyer Language Miner)",
        "differential": "Extractor de investigación GTM que extrae frases reales de dolor de clientes ('buyer language'), menciones a la competencia y ángulos de contenido sin requerir API keys de Reddit, exportando Markdown estructurado optimizado para LLMs.",
        "preferred_files": ["find.py", "reddit.py", "main.py", "README.md"]
    },
    "reddit-agent-langgraph": {
        "title": "Reddit Agent (LangGraph State Machine)",
        "differential": "Agente autónomo de engagement para Reddit implementado con LangGraph: orquesta una máquina de estados para descubrimiento de publicaciones emergentes, scoring de calidad con IA y aprobación humana (Human-in-the-Loop) vía Slack/Telegram.",
        "preferred_files": ["agent.py", "graph.py", "reddit_client.py", "main.py"]
    },
    "reddit-research-mcp": {
        "title": "Reddit Research MCP Server",
        "differential": "Servidor MCP (Model Context Protocol) que habilita búsqueda semántica sobre más de 20,000 subreddits, recuperación de hilos con citaciones verificadas y análisis competitivo asistido por IA para Claude Desktop, Cursor y Gemini.",
        "preferred_files": ["src/index.ts", "src/server.ts", "package.json", "README.md"]
    },
    "n8n-reddit-scraper": {
        "title": "n8n Reddit Buying-Intent Scraper & Workflows",
        "differential": "Suite de workflows visuales listos para importar en n8n para capturar leads con intención de compra en Reddit, sincronizarlos a CRMs/Slack y conectarlos con agentes de IA vía protocolo MCP.",
        "preferred_files": ["workflows/", "README.md"]
    },
    "reddit-streaming-pipeline": {
        "title": "Reddit Real-Time Streaming Big Data Pipeline",
        "differential": "Arquitectura de streaming distribuido a gran escala: consume comentarios continuos de Reddit vía Kafka, los procesa y agrega en tiempo real con Apache Spark Streaming, los persiste en Cassandra y los visualiza en Grafana.",
        "preferred_files": ["spark_streaming.py", "kafka_producer.py", "docker-compose.yml", "README.md"]
    },
    "reddit-sentiment-analysis-fullstack": {
        "title": "Reddit Sentiment Analysis Platform (React + Flask)",
        "differential": "Plataforma full-stack desacoplada (Frontend React + Backend Flask) con clasificadores de Machine Learning entrenados para predecir polaridad de hilos y generar reportes gráficos de percepción de marca.",
        "preferred_files": ["backend/app.py", "backend/model.py", "frontend/src/App.js", "README.md"]
    },
    "reddit-kb-mcp-server": {
        "title": "Reddit Knowledge Base MCP Server (ChromaDB)",
        "differential": "Servidor MCP que convierte el archivo y guardados de Reddit en una base de conocimiento vectorial indexada en ChromaDB, permitiendo a asistentes de IA realizar consultas semánticas y RAG sobre hilos complejos.",
        "preferred_files": ["server.py", "chroma_client.py", "requirements.txt", "README.md"]
    },
    "multimodal-reddit-search": {
        "title": "Multimodal Reddit Search (CLIP + Qdrant)",
        "differential": "Motor de búsqueda vectorial multimodal que ingesta posts de Reddit, genera representaciones vectoriales conjuntas de texto e imágenes mediante OpenAI CLIP y las indexa en Qdrant para búsquedas cruzadas texto-imagen.",
        "preferred_files": ["search.py", "ingest.py", "app.py", "README.md"]
    },
    "reddit-sentiment-zero-shot": {
        "title": "Reddit Sentiment Zero-Shot NLI Pipeline",
        "differential": "Pipeline de investigación en NLP para clasificar hilos de discusión de Reddit usando modelos Zero-Shot basados en Inferencia de Lenguaje Natural (NLI), permitiendo categorizar quejas e intenciones sin requerir datos etiquetados previos.",
        "preferred_files": ["sentiment_analysis.py", "zero_shot.py", "preprocess.py", "README.md"]
    },
    "reddit-hole-playwright": {
        "title": "Reddit Hole (Playwright Headless Automation)",
        "differential": "Crawler headless basado en Playwright para sortear protecciones de renderizado dinámico en JavaScript de Reddit, emular interacciones humanas y extraer posts y metadatos sin depender del API oficial.",
        "preferred_files": ["scraper.py", "crawler.py", "main.py", "package.json"]
    },
    "lancedb-vectordb-recipes": {
        "title": "LanceDB Serverless Vector Storage Recipes",
        "differential": "Patrones de diseño de LanceDB para almacenamiento vectorial serverless en disco (formato columnar Lance) con pipelines de RAG y clustering de baja latencia sobre posts y comentarios de Reddit sin costo de servidor.",
        "preferred_files": ["examples/", "tutorials/", "README.md"]
    },
    "vectfox-hybrid-search": {
        "title": "VectFox (Qdrant Hybrid Search & RAG Memory)",
        "differential": "Sistema de memoria RAG y búsqueda híbrida (embeddings densos + léxico disperso) implementado sobre la base de datos vectorial Qdrant para recuperación contextual y summarization de discusiones extensas de Reddit.",
        "preferred_files": ["src/", "vectfox/", "main.py", "README.md"]
    }
}

def analyze_all():
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        results = json.load(f)

    catalog = []
    print("=== INICIANDO ANALISIS RIGUROSO DE CODIGO ===")

    for item in results:
        repo_id = item["id"]
        repo_path = Path(item["folder"])
        owner = item["owner"]
        repo = item["repo"]
        url = item["url"]
        category = item["category"]

        meta = REPO_METADATA.get(repo_id, {})
        title = meta.get("title", f"{owner}/{repo}")
        differential = meta.get("differential", item.get("reason", "Herramienta de referencia para análisis de Reddit."))
        preferred = meta.get("preferred_files", [])

        # Verificar qué archivos preferidos existen físicamente
        actual_files = []
        for pf in preferred:
            target = repo_path / pf
            if target.exists():
                actual_files.append(pf)

        # Si faltan archivos, buscar con heurística de scoring
        if len(actual_files) < 2:
            all_files = [str(f.relative_to(repo_path)).replace("\\", "/") 
                         for f in repo_path.glob("**/*") 
                         if f.is_file() and not any(x in str(f) for x in ['.git', 'node_modules', '__pycache__', '.pytest_cache', 'venv', '.next', 'dist'])]
            
            def score(f):
                s = 0
                fl = f.lower()
                if any(k in fl for k in ['reddit', 'scrape', 'pain', 'idea', 'lead', 'sentiment', 'market', 'bertopic', 'nlp', 'model', 'agent', 'mcp', 'client', 'search', 'workflow', 'pipeline', 'extractor']): s += 10
                if any(k in fl for k in ['main.', 'app.', 'index.', 'router.', 'server.', 'cli.', 'urs.', 'gemini.']): s += 5
                if fl.endswith(('.py', '.rs', '.ts', '.tsx', '.go', '.json', '.md')): s += 3
                if any(x in fl for x in ['test', 'setup.py', 'conftest', '.lock', 'license', 'docker', 'eslint']): s -= 5
                return s

            all_files.sort(key=score, reverse=True)
            for cand in all_files:
                if cand not in actual_files:
                    actual_files.append(cand)
                if len(actual_files) >= 4:
                    break

        file_count = sum(1 for _ in repo_path.glob("**/*") if _.is_file() and ".git" not in str(_))
        catalog.append({
            "id": repo_id,
            "name": title,
            "owner": owner,
            "repo": repo,
            "url": url,
            "category": category,
            "differential_technique": differential,
            "key_files": actual_files[:4],
            "file_count": file_count,
            "local_path": str(repo_path),
            "status": "ready"
        })

    with open(CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    print(f"Analisis completado exitosamente: {len(catalog)} repositorios procesados.")
    print(f"Catalogo guardado en: {CATALOG_FILE}")

if __name__ == "__main__":
    analyze_all()
