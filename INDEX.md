# Reddit Intelligence Radar — Colección Maestra de Repositorios

> Repositorio local de referencia e ingeniería inversa para extracción masiva de datos en Reddit, minería semántica de puntos de dolor (*pain points*), detección algorítmica de demanda (*leads & buying intent*), bases de datos vectoriales y aceleración de micro-SaaS.

- **Ubicación en disco**: `F:\reddit_intelligence_radar\repos\`
- **Total de proyectos investigados y activos**: 57
- **Lote 1 (Base + Expansión Inicial)**: 45 repositorios
- **Lote 2 (Nueva Expansión Diferencial)**: 12 repositorios
- **Tasa de éxito de clonación**: 100% (57/57)

---

## 1. Tabla Maestra Consolidada de Proyectos (57 Repositorios)

| Nombre del Proyecto | URL | Técnica Única que Aporta | Archivos/Módulos Clave para Estudiar |
|---|---|---|---|
| [reddit-painpointer](https://github.com/the-wc/reddit-painpointer.git) | https://github.com/the-wc/reddit-painpointer.git | Filtro léxico y heurístico de quejas recurrentes ('I hate when', 'Is there any tool', 'struggling with') con extracción y clasificación de dolor B2B sobre comunidades de nicho. | `repos/reddit-painpointer/app/lib/reddit.ts`<br>`repos/reddit-painpointer/app/routes/subreddit.tsx`<br>`repos/reddit-painpointer/app/root.tsx`<br>`repos/reddit-painpointer/package.json` |
| [reddit-pain-point-analyzer](https://github.com/thebarbariangroup/reddit-pain-point-analyzer.git) | https://github.com/thebarbariangroup/reddit-pain-point-analyzer.git | Pipeline de análisis de quejas de usuarios con métricas de severidad y frecuencia para agencias de investigación de mercado y lanzamientos de producto. | `repos/reddit-pain-point-analyzer/reddit_analyzer.py`<br>`repos/reddit-pain-point-analyzer/app.py`<br>`repos/reddit-pain-point-analyzer/templates/index.html`<br>`repos/reddit-pain-point-analyzer/requirements.txt` |
| [saas-idea-finder](https://github.com/Curt-Park/saas-idea-finder.git) | https://github.com/Curt-Park/saas-idea-finder.git | Arquitectura multi-agente para correspondencia problema-solución: mapea comunidades, detecta peticiones de producto insatisfechas y sugiere características MVP diferenciadoras. | `repos/saas-idea-finder/src/agents/problem_analyzer.py`<br>`repos/saas-idea-finder/src/agents/competitive_landscape_analyzer.py`<br>`repos/saas-idea-finder/src/agents/mvp_feature_suggester.py`<br>`repos/saas-idea-finder/main.py` |
| [Atalaia (Desktop Lead Listener)](https://github.com/mascanho/Atalaia.git) | https://github.com/mascanho/Atalaia.git | Plataforma de escritorio (Next.js + Tauri + Rust) para social listening y generación de leads: monitoriza intenciones de compra en Reddit y ejecuta análisis contextual con Google Gemini. | `repos/Atalaia/src-tauri/src/ai/gemini.rs`<br>`repos/Atalaia/src/components/leads-generator.tsx`<br>`repos/Atalaia/src/components/reddit-search/index.ts`<br>`repos/Atalaia/src-tauri/src/models/search.rs` |
| [Reddit-Product-Sentiment-Analytics](https://github.com/Peris-Wallace/Reddit-Product-Sentiment-Analytics.git) | https://github.com/Peris-Wallace/Reddit-Product-Sentiment-Analytics.git | Matriz de sentimiento granular por facetas de producto (precio, UX, estabilidad, servicio al cliente) utilizando modelos de NLP sobre hilos técnicos. | `repos/Reddit-Product-Sentiment-Analytics/scraper.py`<br>`repos/Reddit-Product-Sentiment-Analytics/src/sample_scraper_with_search_terms.py`<br>`repos/Reddit-Product-Sentiment-Analytics/src/sample_top_posts_scraper.py` |
| [Pushshift API Core](https://github.com/pushshift/api.git) | https://github.com/pushshift/api.git | Arquitectura de backend para indexación y consulta a escala de petabytes de publicaciones y comentarios históricos de Reddit mediante Elasticsearch y PostgreSQL. | `repos/pushshift-api/api/api.py`<br>`repos/pushshift-api/api/Comment.py`<br>`repos/pushshift-api/api/DBFunctions.py` |
| [Bulk Downloader for Reddit (BDFR)](https://github.com/aliparlakci/bulk-downloader-for-reddit.git) | https://github.com/aliparlakci/bulk-downloader-for-reddit.git | Descargador concurrente con multithreading resiliente, resolución automatizada de URLs CDN (v.redd.it, imgur, gfycat) y deduplicación basada en hashing de contenido. | `repos/bulk-downloader-for-reddit/bdfr/site_downloaders/delay_for_reddit.py`<br>`repos/bulk-downloader-for-reddit/bdfr/site_downloaders/vreddit.py`<br>`repos/bulk-downloader-for-reddit/bdfr/downloader.py` |
| [PandasAI](https://github.com/gventuri/pandas-ai.git) | https://github.com/gventuri/pandas-ai.git | Agente RAG tabular conversacional: transforma lenguaje natural en código Pandas ejecutable y consultas estadísticas, ideal para interrogar datasets de quejas de Reddit. | `repos/pandas-ai/pandasai/agent/base.py`<br>`repos/pandas-ai/pandasai/agent/state.py`<br>`repos/pandas-ai/pandasai/smart_dataframe/` |
| [reddit-market-analyzer](https://github.com/Firstbober/reddit-market-analyzer.git) | https://github.com/Firstbober/reddit-market-analyzer.git | Scoring algorítmico de intención de compra (Buying Intent Index) y detección de debilidades de la competencia para validar demanda comercial de micro-SaaS. | `repos/reddit-market-analyzer/market_analyzer.py`<br>`repos/reddit-market-analyzer/src/analysis/llm_client.py`<br>`repos/reddit-market-analyzer/src/product_ideas/ideator.py` |
| [reddit-market-research](https://github.com/neonwatty/reddit-market-research.git) | https://github.com/neonwatty/reddit-market-research.git | Monitoreo continuo de nichos de mercado en Reddit con categorización automática de publicaciones por relevancia comercial y engagement. | `repos/reddit-market-research/reddit_monitor.py`<br>`repos/reddit-market-research/tests/test_reddit_monitor.py`<br>`repos/reddit-market-research/pyproject.toml` |
| [pain-miner](https://github.com/AdvancingTitans/pain-miner.git) | https://github.com/AdvancingTitans/pain-miner.git | Minería semántica de dolor extrayendo oraciones de frustración de usuarios mediante modelos de clasificación de texto y generación de informes de oportunidad. | `repos/pain-miner/painminer/analysis.py`<br>`repos/pain-miner/painminer/models.py`<br>`repos/pain-miner/painminer/report.py` |
| [reddit-pain-points](https://github.com/lefttree/reddit-pain-points.git) | https://github.com/lefttree/reddit-pain-points.git | Scraper y analizador dual (público y autenticado) para agrupar quejas de clientes y categorizar puntos de dolor sin resolver. | `repos/reddit-pain-points/backend/scraper.py`<br>`repos/reddit-pain-points/backend/scraper_public.py`<br>`repos/reddit-pain-points/backend/cli.py` |
| [RedditLens](https://github.com/0xMassi/redditlens.git) | https://github.com/0xMassi/redditlens.git | Herramienta analítica visual construida en TypeScript para explorar el pulso y sentimiento de comunidades en Reddit mediante interacción directa con la API. | `repos/redditlens/src/reddit.ts`<br>`repos/redditlens/src/cli.ts`<br>`repos/redditlens/src/http.ts`<br>`repos/redditlens/package.json` |
| [ScrapeGraphAI](https://github.com/ScrapeGraphAI/Scrapegraph-ai.git) | https://github.com/ScrapeGraphAI/Scrapegraph-ai.git | Extracción web basada en grafos de razonamiento con LLMs: sintetiza esquemas de datos estructurados de foros y páginas web sin depender de selectores CSS rígidos. | `repos/Scrapegraph-ai/scrapegraphai/graphs/smart_scraper_graph.py`<br>`repos/Scrapegraph-ai/scrapegraphai/nodes/parse_node.py` |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp.git) | https://github.com/yt-dlp/yt-dlp.git | Extractor de medios de Reddit (`extractor/reddit.py`): arquitectura de bypass de tokens de sesión, reconstrucción de streams DASH/HLS de audio/video y evasión de bloqueos. | `repos/yt-dlp/yt_dlp/extractor/reddit.py`<br>`repos/yt-dlp/yt_dlp/extractor/common.py`<br>`repos/yt-dlp/yt_dlp/downloader/common.py` |
| [idea-box](https://github.com/mothivenkatesh/idea-box.git) | https://github.com/mothivenkatesh/idea-box.git | Dataset estructurado de 1000 pain points validados para Vertical AI con análisis de Persona, TAM y Willingness-To-Pay (WTP), con utilidades de ingesta. | `repos/idea-box/scripts/add-pain.py`<br>`repos/idea-box/data/pains-01-repair-home-services.json`<br>`repos/idea-box/data/pains-02-marketing-gtm-revops.json`<br>`repos/idea-box/README.md` |
| [FrictionLog](https://github.com/Medalcode/FrictionLog.git) | https://github.com/Medalcode/FrictionLog.git | Framework estructurado para registrar y categorizar fricciones técnicas, bloqueos de adopción y experiencias negativas detectadas en retroalimentación de usuarios. | `repos/FrictionLog/llm_client.py`<br>`repos/FrictionLog/AGENTS.md`<br>`repos/FrictionLog/docs/agents.md` |
| [painpoint-atlas (Opportunity Radar)](https://github.com/kelvinlee97/painpoint-atlas.git) | https://github.com/kelvinlee97/painpoint-atlas.git | Radar de oportunidades de negocio con modelos de datos para cuantificar la intensidad de problemas y scripts de orquestación de mercado. | `repos/painpoint-atlas/opportunity_radar/models.py`<br>`repos/painpoint-atlas/opportunity_radar/cli.py`<br>`repos/painpoint-atlas/tests/test_workflow_security.py` |
| [reddit-pain-workflow](https://github.com/minirr890112-byte/reddit-pain-workflow.git) | https://github.com/minirr890112-byte/reddit-pain-workflow.git | Pipeline CLI de extracción y síntesis automatizada de dolor en Reddit, diseñado para integrarse con herramientas de automatización CI/CD. | `repos/reddit-pain-workflow/reddit_pain/cli.py`<br>`repos/reddit-pain-workflow/reddit_pain_workflow.py`<br>`repos/reddit-pain-workflow/reddit_pain/__init__.py` |
| [pain-to-pip-package](https://github.com/minirr890112-byte/pain-to-pip-package.git) | https://github.com/minirr890112-byte/pain-to-pip-package.git | Metodología automatizada de conversión de dolores de desarrollo extraídos en Reddit hacia la generación de especificaciones de librerías Python instalables. | `repos/pain-to-pip-package/pain_to_pip/cli.py`<br>`repos/pain-to-pip-package/pipeline.py`<br>`repos/pain-to-pip-package/pain_to_pip/__init__.py` |
| [LiteLLM](https://github.com/BerriAI/litellm.git) | https://github.com/BerriAI/litellm.git | Capa gateway universal de LLMs: gestiona conmutación por error (fallbacks), balanceo de carga, control estricto de presupuestos de tokens y caché para pipelines de scraping masivo. | `repos/litellm/litellm/router.py`<br>`repos/litellm/litellm/main.py`<br>`repos/litellm/litellm/proxy/proxy_server.py` |
| [browserless/chrome](https://github.com/browserless/chrome.git) | https://github.com/browserless/chrome.git | Infraestructura de headless Chrome en contenedores con API REST para scraping de SPAs, evasión de desafíos Cloudflare y captura de DOM completo de Reddit. | `repos/browserless-chrome/src/shared/scrape.http.ts`<br>`repos/browserless-chrome/src/routes/chrome/http/scrape.post.ts`<br>`repos/browserless-chrome/package.json` |
| [Full Stack FastAPI Template](https://github.com/tiangolo/full-stack-fastapi-template.git) | https://github.com/tiangolo/full-stack-fastapi-template.git | Arquitectura de producción lista para lanzar micro-SaaS: backend FastAPI asíncrono, autenticación JWT, modelos SQLModel/PostgreSQL y frontend React. | `repos/full-stack-fastapi-template/backend/app/models.py`<br>`repos/full-stack-fastapi-template/backend/app/api/main.py`<br>`repos/full-stack-fastapi-template/backend/app/core/db.py`<br>`repos/full-stack-fastapi-template/frontend/src/client/index.ts` |
| [posthog-js](https://github.com/PostHog/posthog-js.git) | https://github.com/PostHog/posthog-js.git | SDK de instrumentación para validación de demanda: seguimiento de conversión en botones de lista de espera ('Join Waitlist'), mapas de calor y analítica de retención. | `repos/posthog-js/packages/ai/src/claude-agent-sdk/index.ts`<br>`repos/posthog-js/packages/ai/src/openai-agents/index.ts` |
| [ArchiveBox](https://github.com/ArchiveBox/ArchiveBox.git) | https://github.com/ArchiveBox/ArchiveBox.git | Plataforma de preservación web autoalojada con servidor MCP integrado, captura de texto completo e indexación de páginas para resguardar evidencia eliminada. | `repos/ArchiveBox/archivebox/mcp/server.py`<br>`repos/ArchiveBox/archivebox/core/models.py` |
| [RedoraAI](https://github.com/donebyai-team/RedoraAI.git) | https://github.com/donebyai-team/RedoraAI.git | Plataforma de prospección automatizada en Reddit impulsada por agentes autónomos en Go y clientes web en TypeScript para detección de leads e interacciones no invasivas. | `repos/RedoraAI/backend/agents/agents.go`<br>`repos/RedoraAI/backend/agents/agents_enum.go`<br>`repos/RedoraAI/frontend/packages/client/index.ts` |
| [redsignal](https://github.com/ivucicev/redsignal.git) | https://github.com/ivucicev/redsignal.git | Monitor de Reddit con filtrado de ruido por IA (compatible con Ollama y OpenAI) y panel de control web para calificar y responder oportunidades comerciales. | `repos/redsignal/app.py`<br>`repos/redsignal/frontend/index.html`<br>`repos/redsignal/static/index.html` |
| [Reddit_Scrapper (Mohamed Saleh)](https://github.com/Mohamedsaleh14/Reddit_Scrapper.git) | https://github.com/Mohamedsaleh14/Reddit_Scrapper.git | Extractor de problemas de mercado con módulo de control de tasa (`rate_limiter.py`), descubrimiento de subreddits y análisis de dolor vía modelos GPT. | `repos/mohamedsaleh-reddit-scrapper/reddit/rate_limiter.py`<br>`repos/mohamedsaleh-reddit-scrapper/reddit/discovery.py`<br>`repos/mohamedsaleh-reddit-scrapper/reddit/scraper.py` |
| [Business Ideas Dataset](https://github.com/theomarsoliman/business-ideas-dataset.git) | https://github.com/theomarsoliman/business-ideas-dataset.git | Catálogo estructurado de ideas de negocio y oportunidades B2B minadas directamente de Reddit y reviews públicas, con scoring de viabilidad y severidad de problema. | `repos/business-ideas-dataset/data/ideas.csv`<br>`repos/business-ideas-dataset/data/ideas.json`<br>`repos/business-ideas-dataset/examples/app-ideas.md`<br>`repos/business-ideas-dataset/README.md` |
| [Reddit NLP Analytics](https://github.com/pranjal-pravesh/Reddit-NLP-Analytics.git) | https://github.com/pranjal-pravesh/Reddit-NLP-Analytics.git | Pipeline de NLP completo que une la ingesta de Reddit con modelado de tópicos BERTopic (c-TF-IDF + embeddings) y análisis de sentimiento con modelos RoBERTa. | `repos/reddit-nlp-analytics/app/services/nlp_service.py`<br>`repos/reddit-nlp-analytics/app/services/reddit_client.py`<br>`repos/reddit-nlp-analytics/app/api/v1/endpoints/reddit.py` |
| [Reddit-Intelligence](https://github.com/veluthoor/Reddit-Intelligence.git) | https://github.com/veluthoor/Reddit-Intelligence.git | Suite de agregación de inteligencia competitiva con backend FastAPI y servicios especializados de scraping (`scraper_service.py`) para monitorear feedback. | `repos/reddit-intelligence/backend/app/scraper_service.py`<br>`repos/reddit-intelligence/backend/app/models.py`<br>`repos/reddit-intelligence/backend/app/main.py` |
| [BuildRadar Reddit Intel Agent MCP](https://github.com/Houseofmvps/reddit-intel-agent-mcp.git) | https://github.com/Houseofmvps/reddit-intel-agent-mcp.git | Servidor MCP (Model Context Protocol) para asistentes de IA que expone herramientas de scoring de oportunidad, tracking de competidores y prospección de leads en Reddit. | `repos/reddit-intel-agent-mcp/src/intelligence/subreddit-analyzer.ts`<br>`repos/reddit-intel-agent-mcp/src/api/reddit-oauth.ts`<br>`repos/reddit-intel-agent-mcp/src/reddit/client.ts`<br>`repos/reddit-intel-agent-mcp/src/index.ts` |
| [Reddit Pain Research Skill](https://github.com/haseebeqx/reddit-pain-research-skill.git) | https://github.com/haseebeqx/reddit-pain-research-skill.git | Skill modular de agente de IA para planificar estudios de mercado en comunidades de Reddit, agrupar evidencia empírica y generar hipótesis de monetización. | `repos/reddit-pain-research-skill/reddit-pain-research/SKILL.md`<br>`repos/reddit-pain-research-skill/reddit-pain-research/scripts/build_reports.py`<br>`repos/reddit-pain-research-skill/reddit-pain-research/scripts/create_research_config.py` |
| [Social Listening Tool](https://github.com/phil-morton/social-listening-tool.git) | https://github.com/phil-morton/social-listening-tool.git | Script ligero de captura continua de menciones en Reddit (`reddit-pull.py`) con exportación estructurada a JSONL para procesamiento analítico en downstream. | `repos/social-listening-tool/reddit-pull.py`<br>`repos/social-listening-tool/README.md` |
| [MiloAgent](https://github.com/SoCloseSociety/MiloAgent.git) | https://github.com/SoCloseSociety/MiloAgent.git | Agente autónomo de crecimiento multi-comunidad con motor de investigación (`research_engine.py`) y hub de gestión de subreddits (`subreddit_hub.py`). | `repos/milo-agent/miloagent.py`<br>`repos/milo-agent/core/research_engine.py`<br>`repos/milo-agent/core/subreddit_hub.py` |
| [snscrape](https://github.com/JustAnotherArchivist/snscrape.git) | https://github.com/JustAnotherArchivist/snscrape.git | Extracción sin autenticación vía protocolo público de Reddit (`snscrape/modules/reddit.py`), prescindiendo de credenciales y evitando bloqueos de API. | `repos/snscrape/snscrape/modules/reddit.py`<br>`repos/snscrape/snscrape/_cli.py`<br>`repos/snscrape/snscrape/base.py` |
| [Crawlee for Python](https://github.com/apify/crawlee-python.git) | https://github.com/apify/crawlee-python.git | Framework de crawling profesional con soporte para Playwright, rotación inteligente de proxies, emulación de huella TLS/HTTP2 (`curl-impersonate`) y colas de URLs. | `repos/crawlee-python/docs/guides/code_examples/http_clients/parsel_curl_impersonate_example.py`<br>`repos/crawlee-python/src/crawlee/crawlers/`<br>`repos/crawlee-python/src/crawlee/sessions/` |
| [Awesome AI Lead Generation](https://github.com/toofast1/awesome-ai-lead-generation.git) | https://github.com/toofast1/awesome-ai-lead-generation.git | Directorio exhaustivo de herramientas, frameworks y arquitecturas probadas para generación de leads e identificación de intención comercial con IA. | `repos/awesome-ai-lead-generation/README.md`<br>`repos/awesome-ai-lead-generation/CONTRIBUTING.md` |
| [Awesome Reddit Lead Gen](https://github.com/jeeiee/awesome-reddit-lead-gen.git) | https://github.com/jeeiee/awesome-reddit-lead-gen.git | Guía táctica de prospección comercial en Reddit: mapeo de subreddits de alto valor, plantillas de búsqueda booleana y reglas anti-baneo de la comunidad. | `repos/awesome-reddit-lead-gen/README.md` |
| [Reddit Lupus Pain NLP](https://github.com/bozlab/reddit-lupus-pain-nlp.git) | https://github.com/bozlab/reddit-lupus-pain-nlp.git | Implementación práctica de modelado de tópicos con BERTopic aplicada a la extracción de quejas y dolor en hilos de salud, con vocabulario léxico curado. | `repos/reddit-lupus-pain-nlp/pain_vocabulary_lupus_reddit.xlsx`<br>`repos/reddit-lupus-pain-nlp/one-sentence/1 - single_sentence_topic_modeling.ipynb`<br>`repos/reddit-lupus-pain-nlp/Topic modeling details.docx` |
| [Reddit Core (Historical Monolith)](https://github.com/reddit-archive/reddit.git) | https://github.com/reddit-archive/reddit.git | Código fuente original del backend de Reddit: controladores base, modelos de Thing/Account/Comment y algoritmos de búsqueda y ranking de subreddits. | `repos/reddit-archive-core/r2/r2/controllers/reddit_base.py`<br>`repos/reddit-archive-core/r2/r2/lib/subreddit_search.py` |
| [PRAW (Python Reddit API Wrapper)](https://github.com/praw-dev/praw.git) | https://github.com/praw-dev/praw.git | SDK oficial y estándar industrial en Python: autenticación OAuth2 transparente, auto-throttling según rate limits oficiales de Reddit (60 req/min) y streams perezosos de posts y comentarios. | `repos/praw/praw/reddit.py`<br>`repos/praw/praw/models/listing/mixins/subreddit.py`<br>`repos/praw/praw/models/reddit/comment.py` |
| [Async PRAW](https://github.com/praw-dev/asyncpraw.git) | https://github.com/praw-dev/asyncpraw.git | Implementación asíncrona de alto rendimiento construida sobre aiohttp y asyncio, diseñada para consumir streams de múltiples subreddits concurrentes sin bloquear el hilo principal. | `repos/asyncpraw/asyncpraw/reddit.py`<br>`repos/asyncpraw/asyncpraw/models/reddit/submission.py`<br>`repos/asyncpraw/asyncpraw/models/auth.py` |
| [Bellingcat Reddit Post Scraping Tool](https://github.com/bellingcat/reddit-post-scraping-tool.git) | https://github.com/bellingcat/reddit-post-scraping-tool.git | Metodología OSINT forense para búsqueda de evidencia por palabras clave en Reddit con preservación estricta de marcas de tiempo UTC, IDs y metadatos de autor. | `repos/bellingcat-reddit-post-scraping-tool/rpst/scraper.py`<br>`repos/bellingcat-reddit-post-scraping-tool/rpst/api.py`<br>`repos/bellingcat-reddit-post-scraping-tool/rpst/base.py` |
| [Universal Reddit Scraper (URS)](https://github.com/JosephLai241/URS.git) | https://github.com/JosephLai241/URS.git | CLI de scraping forense exhaustivo sin overhead, con soporte para recolección de comentarios anidados multinivel, feeds en vivo (Livestream) y perfiles en JSON/CSV. | `repos/urs-reddit-scraper/urs/praw_scrapers/live_scrapers/Livestream.py`<br>`repos/urs-reddit-scraper/urs/Urs.py`<br>`repos/urs-reddit-scraper/urs/utils/DirInit.py` |
| [reddit-find (GTM Buyer Language Miner) 🔥 `[Lote 2]`](https://github.com/LeadGrowGTM/reddit-find.git) | https://github.com/LeadGrowGTM/reddit-find.git | Extractor de investigación GTM que extrae frases reales de dolor de clientes ('buyer language'), menciones a la competencia y ángulos de contenido sin requerir API keys de Reddit, exportando Markdown estructurado optimizado para LLMs. | `repos/reddit-find/README.md`<br>`repos/reddit-find/reddit_find/cli.py`<br>`repos/reddit-find/AGENTS.md`<br>`repos/reddit-find/reddit_find/discover.py` |
| [Reddit Agent (LangGraph State Machine) 🔥 `[Lote 2]`](https://github.com/avisangle/reddit_agent.git) | https://github.com/avisangle/reddit_agent.git | Agente autónomo de engagement para Reddit implementado con LangGraph: orquesta una máquina de estados para descubrimiento de publicaciones emergentes, scoring de calidad con IA y aprobación humana (Human-in-the-Loop) vía Slack/Telegram. | `repos/reddit-agent-langgraph/main.py`<br>`repos/reddit-agent-langgraph/Reddit_Comment_Engagement_Agent_PRD_v2.1.md`<br>`repos/reddit-agent-langgraph/agents/generator.py`<br>`repos/reddit-agent-langgraph/agents/__init__.py` |
| [Reddit Research MCP Server 🔥 `[Lote 2]`](https://github.com/dialog-tools/reddit-research-mcp.git) | https://github.com/dialog-tools/reddit-research-mcp.git | Servidor MCP (Model Context Protocol) que habilita búsqueda semántica sobre más de 20,000 subreddits, recuperación de hilos con citaciones verificadas y análisis competitivo asistido por IA para Claude Desktop, Cursor y Gemini. | `repos/reddit-research-mcp/package.json`<br>`repos/reddit-research-mcp/README.md` |
| [n8n Reddit Buying-Intent Scraper & Workflows 🔥 `[Lote 2]`](https://github.com/gguyon0925/n8n-reddit-scraper.git) | https://github.com/gguyon0925/n8n-reddit-scraper.git | Suite de workflows visuales listos para importar en n8n para capturar leads con intención de compra en Reddit, sincronizarlos a CRMs/Slack y conectarlos con agentes de IA vía protocolo MCP. | `repos/n8n-reddit-scraper/README.md`<br>`repos/n8n-reddit-scraper/mcp/claude-desktop.json`<br>`repos/n8n-reddit-scraper/mcp/cursor.json`<br>`repos/n8n-reddit-scraper/mcp/README.md` |
| [Reddit Real-Time Streaming Big Data Pipeline 🔥 `[Lote 2]`](https://github.com/nama1arpit/reddit-streaming-pipeline.git) | https://github.com/nama1arpit/reddit-streaming-pipeline.git | Arquitectura de streaming distribuido a gran escala: consume comentarios continuos de Reddit vía Kafka, los procesa y agrega en tiempo real con Apache Spark Streaming, los persiste en Cassandra y los visualiza en Grafana. | `repos/reddit-streaming-pipeline/README.md`<br>`repos/reddit-streaming-pipeline/reddit_producer/reddit_producer.py`<br>`repos/reddit-streaming-pipeline/images/Reddit Sentiment Analysis Data Pipeline.drawio.png`<br>`repos/reddit-streaming-pipeline/images/top_subreddit_panel.png` |
| [Reddit Sentiment Analysis Platform (React + Flask) 🔥 `[Lote 2]`](https://github.com/netto14cr/reddit_sentiment_analysis.git) | https://github.com/netto14cr/reddit_sentiment_analysis.git | Plataforma full-stack desacoplada (Frontend React + Backend Flask) con clasificadores de Machine Learning entrenados para predecir polaridad de hilos y generar reportes gráficos de percepción de marca. | `repos/reddit-sentiment-analysis-fullstack/README.md`<br>`repos/reddit-sentiment-analysis-fullstack/sentiment_analysis_backend/app.py`<br>`repos/reddit-sentiment-analysis-fullstack/sentiment_analysis_backend/app_launcher/run_app.py`<br>`repos/reddit-sentiment-analysis-fullstack/sentiment_analysis_backend/app.log` |
| [Reddit Knowledge Base MCP Server (ChromaDB) 🔥 `[Lote 2]`](https://github.com/lh1207/reddit-kb-mcp-server.git) | https://github.com/lh1207/reddit-kb-mcp-server.git | Servidor MCP que convierte el archivo y guardados de Reddit en una base de conocimiento vectorial indexada en ChromaDB, permitiendo a asistentes de IA realizar consultas semánticas y RAG sobre hilos complejos. | `repos/reddit-kb-mcp-server/server.py`<br>`repos/reddit-kb-mcp-server/requirements.txt`<br>`repos/reddit-kb-mcp-server/README.md` |
| [Multimodal Reddit Search (CLIP + Qdrant) 🔥 `[Lote 2]`](https://github.com/DaveOkpare/multimodal-search.git) | https://github.com/DaveOkpare/multimodal-search.git | Motor de búsqueda vectorial multimodal que ingesta posts de Reddit, genera representaciones vectoriales conjuntas de texto e imágenes mediante OpenAI CLIP y las indexa en Qdrant para búsquedas cruzadas texto-imagen. | `repos/multimodal-reddit-search/README.md`<br>`repos/multimodal-reddit-search/fetch_reddit_posts.py`<br>`repos/multimodal-reddit-search/main.py`<br>`repos/multimodal-reddit-search/streamlit_app.py` |
| [Reddit Sentiment Zero-Shot NLI Pipeline 🔥 `[Lote 2]`](https://github.com/marta-baratto/Reddit_sentiment.git) | https://github.com/marta-baratto/Reddit_sentiment.git | Pipeline de investigación en NLP para clasificar hilos de discusión de Reddit usando modelos Zero-Shot basados en Inferencia de Lenguaje Natural (NLI), permitiendo categorizar quejas e intenciones sin requerir datos etiquetados previos. | `repos/reddit-sentiment-zero-shot/README.md`<br>`repos/reddit-sentiment-zero-shot/data/amazon_sentiment_series.json`<br>`repos/reddit-sentiment-zero-shot/data/apple_sentiment_series.json`<br>`repos/reddit-sentiment-zero-shot/data/google_sentiment_series.json` |
| [Reddit Hole (Playwright Headless Automation) 🔥 `[Lote 2]`](https://github.com/nssharmaofficial/reddit-hole.git) | https://github.com/nssharmaofficial/reddit-hole.git | Crawler headless basado en Playwright para sortear protecciones de renderizado dinámico en JavaScript de Reddit, emular interacciones humanas y extraer posts y metadatos sin depender del API oficial. | `repos/reddit-hole-playwright/main.py`<br>`repos/reddit-hole-playwright/utils/reddit.py`<br>`repos/reddit-hole-playwright/docs/reddit-banner.png`<br>`repos/reddit-hole-playwright/docs/reddit1.png` |
| [LanceDB Serverless Vector Storage Recipes 🔥 `[Lote 2]`](https://github.com/lancedb/vectordb-recipes.git) | https://github.com/lancedb/vectordb-recipes.git | Patrones de diseño de LanceDB para almacenamiento vectorial serverless en disco (formato columnar Lance) con pipelines de RAG y clustering de baja latencia sobre posts y comentarios de Reddit sin costo de servidor. | `repos/lancedb-vectordb-recipes/examples/`<br>`repos/lancedb-vectordb-recipes/tutorials/`<br>`repos/lancedb-vectordb-recipes/README.md` |
| [VectFox (Qdrant Hybrid Search & RAG Memory) 🔥 `[Lote 2]`](https://github.com/KritBlade/VectFox.git) | https://github.com/KritBlade/VectFox.git | Sistema de memoria RAG y búsqueda híbrida (embeddings densos + léxico disperso) implementado sobre la base de datos vectorial Qdrant para recuperación contextual y summarization de discusiones extensas de Reddit. | `repos/vectfox-hybrid-search/README.md`<br>`repos/vectfox-hybrid-search/.mcp.json`<br>`repos/vectfox-hybrid-search/core/agentic-retrieval.js`<br>`repos/vectfox-hybrid-search/core/eventbase-extractor.js` |

---

## 2. Nueva Expansión (Lote 2): Análisis Diferencial vs. Primeros 45

El Lote 2 incorpora paradigmas computacionales y arquitectónicos ausentes en los primeros 45 repositorios:

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

---

## 3. Mapa Arquitectónico Consolidado por Capas

### Capa: Pain Point Mining

- ✅ **reddit-painpointer** (`reddit-painpointer`): Filtro léxico y heurístico de quejas recurrentes ('I hate when', 'Is there any tool', 'struggling with') con extracción y clasificación de dolor B2B sobre comunidades de nicho.
  - 📄 Archivo clave: `repos/reddit-painpointer/app/lib/reddit.ts`
  - 📄 Archivo clave: `repos/reddit-painpointer/app/routes/subreddit.tsx`
  - 📄 Archivo clave: `repos/reddit-painpointer/app/root.tsx`
  - 📄 Archivo clave: `repos/reddit-painpointer/package.json`
- ✅ **reddit-pain-point-analyzer** (`reddit-pain-point-analyzer`): Pipeline de análisis de quejas de usuarios con métricas de severidad y frecuencia para agencias de investigación de mercado y lanzamientos de producto.
  - 📄 Archivo clave: `repos/reddit-pain-point-analyzer/reddit_analyzer.py`
  - 📄 Archivo clave: `repos/reddit-pain-point-analyzer/app.py`
  - 📄 Archivo clave: `repos/reddit-pain-point-analyzer/templates/index.html`
  - 📄 Archivo clave: `repos/reddit-pain-point-analyzer/requirements.txt`
- ✅ **pain-miner** (`pain-miner`): Minería semántica de dolor extrayendo oraciones de frustración de usuarios mediante modelos de clasificación de texto y generación de informes de oportunidad.
  - 📄 Archivo clave: `repos/pain-miner/painminer/analysis.py`
  - 📄 Archivo clave: `repos/pain-miner/painminer/models.py`
  - 📄 Archivo clave: `repos/pain-miner/painminer/report.py`
- ✅ **reddit-pain-points** (`reddit-pain-points`): Scraper y analizador dual (público y autenticado) para agrupar quejas de clientes y categorizar puntos de dolor sin resolver.
  - 📄 Archivo clave: `repos/reddit-pain-points/backend/scraper.py`
  - 📄 Archivo clave: `repos/reddit-pain-points/backend/scraper_public.py`
  - 📄 Archivo clave: `repos/reddit-pain-points/backend/cli.py`
- ✅ **FrictionLog** (`FrictionLog`): Framework estructurado para registrar y categorizar fricciones técnicas, bloqueos de adopción y experiencias negativas detectadas en retroalimentación de usuarios.
  - 📄 Archivo clave: `repos/FrictionLog/llm_client.py`
  - 📄 Archivo clave: `repos/FrictionLog/AGENTS.md`
  - 📄 Archivo clave: `repos/FrictionLog/docs/agents.md`
- ✅ **painpoint-atlas (Opportunity Radar)** (`painpoint-atlas`): Radar de oportunidades de negocio con modelos de datos para cuantificar la intensidad de problemas y scripts de orquestación de mercado.
  - 📄 Archivo clave: `repos/painpoint-atlas/opportunity_radar/models.py`
  - 📄 Archivo clave: `repos/painpoint-atlas/opportunity_radar/cli.py`
  - 📄 Archivo clave: `repos/painpoint-atlas/tests/test_workflow_security.py`
- ✅ **reddit-pain-workflow** (`reddit-pain-workflow`): Pipeline CLI de extracción y síntesis automatizada de dolor en Reddit, diseñado para integrarse con herramientas de automatización CI/CD.
  - 📄 Archivo clave: `repos/reddit-pain-workflow/reddit_pain/cli.py`
  - 📄 Archivo clave: `repos/reddit-pain-workflow/reddit_pain_workflow.py`
  - 📄 Archivo clave: `repos/reddit-pain-workflow/reddit_pain/__init__.py`

### Capa: Demand & Micro-SaaS Validation

- ✅ **saas-idea-finder** (`saas-idea-finder`): Arquitectura multi-agente para correspondencia problema-solución: mapea comunidades, detecta peticiones de producto insatisfechas y sugiere características MVP diferenciadoras.
  - 📄 Archivo clave: `repos/saas-idea-finder/src/agents/problem_analyzer.py`
  - 📄 Archivo clave: `repos/saas-idea-finder/src/agents/competitive_landscape_analyzer.py`
  - 📄 Archivo clave: `repos/saas-idea-finder/src/agents/mvp_feature_suggester.py`
  - 📄 Archivo clave: `repos/saas-idea-finder/main.py`
- ✅ **reddit-market-analyzer** (`reddit-market-analyzer`): Scoring algorítmico de intención de compra (Buying Intent Index) y detección de debilidades de la competencia para validar demanda comercial de micro-SaaS.
  - 📄 Archivo clave: `repos/reddit-market-analyzer/market_analyzer.py`
  - 📄 Archivo clave: `repos/reddit-market-analyzer/src/analysis/llm_client.py`
  - 📄 Archivo clave: `repos/reddit-market-analyzer/src/product_ideas/ideator.py`
- ✅ **reddit-market-research** (`reddit-market-research`): Monitoreo continuo de nichos de mercado en Reddit con categorización automática de publicaciones por relevancia comercial y engagement.
  - 📄 Archivo clave: `repos/reddit-market-research/reddit_monitor.py`
  - 📄 Archivo clave: `repos/reddit-market-research/tests/test_reddit_monitor.py`
  - 📄 Archivo clave: `repos/reddit-market-research/pyproject.toml`
- ✅ **idea-box** (`idea-box`): Dataset estructurado de 1000 pain points validados para Vertical AI con análisis de Persona, TAM y Willingness-To-Pay (WTP), con utilidades de ingesta.
  - 📄 Archivo clave: `repos/idea-box/scripts/add-pain.py`
  - 📄 Archivo clave: `repos/idea-box/data/pains-01-repair-home-services.json`
  - 📄 Archivo clave: `repos/idea-box/data/pains-02-marketing-gtm-revops.json`
  - 📄 Archivo clave: `repos/idea-box/README.md`
- ✅ **pain-to-pip-package** (`pain-to-pip-package`): Metodología automatizada de conversión de dolores de desarrollo extraídos en Reddit hacia la generación de especificaciones de librerías Python instalables.
  - 📄 Archivo clave: `repos/pain-to-pip-package/pain_to_pip/cli.py`
  - 📄 Archivo clave: `repos/pain-to-pip-package/pipeline.py`
  - 📄 Archivo clave: `repos/pain-to-pip-package/pain_to_pip/__init__.py`
- ✅ **Business Ideas Dataset** (`business-ideas-dataset`): Catálogo estructurado de ideas de negocio y oportunidades B2B minadas directamente de Reddit y reviews públicas, con scoring de viabilidad y severidad de problema.
  - 📄 Archivo clave: `repos/business-ideas-dataset/data/ideas.csv`
  - 📄 Archivo clave: `repos/business-ideas-dataset/data/ideas.json`
  - 📄 Archivo clave: `repos/business-ideas-dataset/examples/app-ideas.md`
  - 📄 Archivo clave: `repos/business-ideas-dataset/README.md`

### Capa: Lead Generation & Social Listening

- ✅ **Atalaia (Desktop Lead Listener)** (`Atalaia`): Plataforma de escritorio (Next.js + Tauri + Rust) para social listening y generación de leads: monitoriza intenciones de compra en Reddit y ejecuta análisis contextual con Google Gemini.
  - 📄 Archivo clave: `repos/Atalaia/src-tauri/src/ai/gemini.rs`
  - 📄 Archivo clave: `repos/Atalaia/src/components/leads-generator.tsx`
  - 📄 Archivo clave: `repos/Atalaia/src/components/reddit-search/index.ts`
  - 📄 Archivo clave: `repos/Atalaia/src-tauri/src/models/search.rs`
- ✅ **Social Listening Tool** (`social-listening-tool`): Script ligero de captura continua de menciones en Reddit (`reddit-pull.py`) con exportación estructurada a JSONL para procesamiento analítico en downstream.
  - 📄 Archivo clave: `repos/social-listening-tool/reddit-pull.py`
  - 📄 Archivo clave: `repos/social-listening-tool/README.md`

### Capa: Sentiment & Intent Analysis

- ✅ **Reddit-Product-Sentiment-Analytics** (`Reddit-Product-Sentiment-Analytics`): Matriz de sentimiento granular por facetas de producto (precio, UX, estabilidad, servicio al cliente) utilizando modelos de NLP sobre hilos técnicos.
  - 📄 Archivo clave: `repos/Reddit-Product-Sentiment-Analytics/scraper.py`
  - 📄 Archivo clave: `repos/Reddit-Product-Sentiment-Analytics/src/sample_scraper_with_search_terms.py`
  - 📄 Archivo clave: `repos/Reddit-Product-Sentiment-Analytics/src/sample_top_posts_scraper.py`
- ✅ **RedditLens** (`redditlens`): Herramienta analítica visual construida en TypeScript para explorar el pulso y sentimiento de comunidades en Reddit mediante interacción directa con la API.
  - 📄 Archivo clave: `repos/redditlens/src/reddit.ts`
  - 📄 Archivo clave: `repos/redditlens/src/cli.ts`
  - 📄 Archivo clave: `repos/redditlens/src/http.ts`
  - 📄 Archivo clave: `repos/redditlens/package.json`

### Capa: Extraction & Ingestion Engines

- ✅ **Pushshift API Core** (`pushshift-api`): Arquitectura de backend para indexación y consulta a escala de petabytes de publicaciones y comentarios históricos de Reddit mediante Elasticsearch y PostgreSQL.
  - 📄 Archivo clave: `repos/pushshift-api/api/api.py`
  - 📄 Archivo clave: `repos/pushshift-api/api/Comment.py`
  - 📄 Archivo clave: `repos/pushshift-api/api/DBFunctions.py`
- ✅ **Bulk Downloader for Reddit (BDFR)** (`bulk-downloader-for-reddit`): Descargador concurrente con multithreading resiliente, resolución automatizada de URLs CDN (v.redd.it, imgur, gfycat) y deduplicación basada en hashing de contenido.
  - 📄 Archivo clave: `repos/bulk-downloader-for-reddit/bdfr/site_downloaders/delay_for_reddit.py`
  - 📄 Archivo clave: `repos/bulk-downloader-for-reddit/bdfr/site_downloaders/vreddit.py`
  - 📄 Archivo clave: `repos/bulk-downloader-for-reddit/bdfr/downloader.py`
- ✅ **ScrapeGraphAI** (`Scrapegraph-ai`): Extracción web basada en grafos de razonamiento con LLMs: sintetiza esquemas de datos estructurados de foros y páginas web sin depender de selectores CSS rígidos.
  - 📄 Archivo clave: `repos/Scrapegraph-ai/scrapegraphai/graphs/smart_scraper_graph.py`
  - 📄 Archivo clave: `repos/Scrapegraph-ai/scrapegraphai/nodes/parse_node.py`

### Capa: Data Transformation & LLM Analytics

- ✅ **PandasAI** (`pandas-ai`): Agente RAG tabular conversacional: transforma lenguaje natural en código Pandas ejecutable y consultas estadísticas, ideal para interrogar datasets de quejas de Reddit.
  - 📄 Archivo clave: `repos/pandas-ai/pandasai/agent/base.py`
  - 📄 Archivo clave: `repos/pandas-ai/pandasai/agent/state.py`
  - 📄 Archivo clave: `repos/pandas-ai/pandasai/smart_dataframe/`

### Capa: Extraction Utilities & Media

- ✅ **yt-dlp** (`yt-dlp`): Extractor de medios de Reddit (`extractor/reddit.py`): arquitectura de bypass de tokens de sesión, reconstrucción de streams DASH/HLS de audio/video y evasión de bloqueos.
  - 📄 Archivo clave: `repos/yt-dlp/yt_dlp/extractor/reddit.py`
  - 📄 Archivo clave: `repos/yt-dlp/yt_dlp/extractor/common.py`
  - 📄 Archivo clave: `repos/yt-dlp/yt_dlp/downloader/common.py`

### Capa: LLM Routing & Gateway

- ✅ **LiteLLM** (`litellm`): Capa gateway universal de LLMs: gestiona conmutación por error (fallbacks), balanceo de carga, control estricto de presupuestos de tokens y caché para pipelines de scraping masivo.
  - 📄 Archivo clave: `repos/litellm/litellm/router.py`
  - 📄 Archivo clave: `repos/litellm/litellm/main.py`
  - 📄 Archivo clave: `repos/litellm/litellm/proxy/proxy_server.py`

### Capa: Headless Crawling & Anti-Bot

- ✅ **browserless/chrome** (`browserless-chrome`): Infraestructura de headless Chrome en contenedores con API REST para scraping de SPAs, evasión de desafíos Cloudflare y captura de DOM completo de Reddit.
  - 📄 Archivo clave: `repos/browserless-chrome/src/shared/scrape.http.ts`
  - 📄 Archivo clave: `repos/browserless-chrome/src/routes/chrome/http/scrape.post.ts`
  - 📄 Archivo clave: `repos/browserless-chrome/package.json`
- ✅ **Crawlee for Python** (`crawlee-python`): Framework de crawling profesional con soporte para Playwright, rotación inteligente de proxies, emulación de huella TLS/HTTP2 (`curl-impersonate`) y colas de URLs.
  - 📄 Archivo clave: `repos/crawlee-python/docs/guides/code_examples/http_clients/parsel_curl_impersonate_example.py`
  - 📄 Archivo clave: `repos/crawlee-python/src/crawlee/crawlers/`
  - 📄 Archivo clave: `repos/crawlee-python/src/crawlee/sessions/`

### Capa: Micro-SaaS Architecture

- ✅ **Full Stack FastAPI Template** (`full-stack-fastapi-template`): Arquitectura de producción lista para lanzar micro-SaaS: backend FastAPI asíncrono, autenticación JWT, modelos SQLModel/PostgreSQL y frontend React.
  - 📄 Archivo clave: `repos/full-stack-fastapi-template/backend/app/models.py`
  - 📄 Archivo clave: `repos/full-stack-fastapi-template/backend/app/api/main.py`
  - 📄 Archivo clave: `repos/full-stack-fastapi-template/backend/app/core/db.py`
  - 📄 Archivo clave: `repos/full-stack-fastapi-template/frontend/src/client/index.ts`

### Capa: Analytics & Validation Feedback

- ✅ **posthog-js** (`posthog-js`): SDK de instrumentación para validación de demanda: seguimiento de conversión en botones de lista de espera ('Join Waitlist'), mapas de calor y analítica de retención.
  - 📄 Archivo clave: `repos/posthog-js/packages/ai/src/claude-agent-sdk/index.ts`
  - 📄 Archivo clave: `repos/posthog-js/packages/ai/src/openai-agents/index.ts`

### Capa: Data Preservation & Archiving

- ✅ **ArchiveBox** (`ArchiveBox`): Plataforma de preservación web autoalojada con servidor MCP integrado, captura de texto completo e indexación de páginas para resguardar evidencia eliminada.
  - 📄 Archivo clave: `repos/ArchiveBox/archivebox/mcp/server.py`
  - 📄 Archivo clave: `repos/ArchiveBox/archivebox/core/models.py`

### Capa: Lead Generation & Outreach

- ✅ **RedoraAI** (`RedoraAI`): Plataforma de prospección automatizada en Reddit impulsada por agentes autónomos en Go y clientes web en TypeScript para detección de leads e interacciones no invasivas.
  - 📄 Archivo clave: `repos/RedoraAI/backend/agents/agents.go`
  - 📄 Archivo clave: `repos/RedoraAI/backend/agents/agents_enum.go`
  - 📄 Archivo clave: `repos/RedoraAI/frontend/packages/client/index.ts`
- ✅ **redsignal** (`redsignal`): Monitor de Reddit con filtrado de ruido por IA (compatible con Ollama y OpenAI) y panel de control web para calificar y responder oportunidades comerciales.
  - 📄 Archivo clave: `repos/redsignal/app.py`
  - 📄 Archivo clave: `repos/redsignal/frontend/index.html`
  - 📄 Archivo clave: `repos/redsignal/static/index.html`

### Capa: Pain Point Mining & UI

- ✅ **Reddit_Scrapper (Mohamed Saleh)** (`mohamedsaleh-reddit-scrapper`): Extractor de problemas de mercado con módulo de control de tasa (`rate_limiter.py`), descubrimiento de subreddits y análisis de dolor vía modelos GPT.
  - 📄 Archivo clave: `repos/mohamedsaleh-reddit-scrapper/reddit/rate_limiter.py`
  - 📄 Archivo clave: `repos/mohamedsaleh-reddit-scrapper/reddit/discovery.py`
  - 📄 Archivo clave: `repos/mohamedsaleh-reddit-scrapper/reddit/scraper.py`

### Capa: Topic Modeling & Clustering

- ✅ **Reddit NLP Analytics** (`reddit-nlp-analytics`): Pipeline de NLP completo que une la ingesta de Reddit con modelado de tópicos BERTopic (c-TF-IDF + embeddings) y análisis de sentimiento con modelos RoBERTa.
  - 📄 Archivo clave: `repos/reddit-nlp-analytics/app/services/nlp_service.py`
  - 📄 Archivo clave: `repos/reddit-nlp-analytics/app/services/reddit_client.py`
  - 📄 Archivo clave: `repos/reddit-nlp-analytics/app/api/v1/endpoints/reddit.py`
- ✅ **Reddit Lupus Pain NLP** (`reddit-lupus-pain-nlp`): Implementación práctica de modelado de tópicos con BERTopic aplicada a la extracción de quejas y dolor en hilos de salud, con vocabulario léxico curado.
  - 📄 Archivo clave: `repos/reddit-lupus-pain-nlp/pain_vocabulary_lupus_reddit.xlsx`
  - 📄 Archivo clave: `repos/reddit-lupus-pain-nlp/one-sentence/1 - single_sentence_topic_modeling.ipynb`
  - 📄 Archivo clave: `repos/reddit-lupus-pain-nlp/Topic modeling details.docx`

### Capa: Market Intelligence

- ✅ **Reddit-Intelligence** (`reddit-intelligence`): Suite de agregación de inteligencia competitiva con backend FastAPI y servicios especializados de scraping (`scraper_service.py`) para monitorear feedback.
  - 📄 Archivo clave: `repos/reddit-intelligence/backend/app/scraper_service.py`
  - 📄 Archivo clave: `repos/reddit-intelligence/backend/app/models.py`
  - 📄 Archivo clave: `repos/reddit-intelligence/backend/app/main.py`

### Capa: MCP & Agentic Search

- ✅ **BuildRadar Reddit Intel Agent MCP** (`reddit-intel-agent-mcp`): Servidor MCP (Model Context Protocol) para asistentes de IA que expone herramientas de scoring de oportunidad, tracking de competidores y prospección de leads en Reddit.
  - 📄 Archivo clave: `repos/reddit-intel-agent-mcp/src/intelligence/subreddit-analyzer.ts`
  - 📄 Archivo clave: `repos/reddit-intel-agent-mcp/src/api/reddit-oauth.ts`
  - 📄 Archivo clave: `repos/reddit-intel-agent-mcp/src/reddit/client.ts`
  - 📄 Archivo clave: `repos/reddit-intel-agent-mcp/src/index.ts`

### Capa: Agent Skills & Research

- ✅ **Reddit Pain Research Skill** (`reddit-pain-research-skill`): Skill modular de agente de IA para planificar estudios de mercado en comunidades de Reddit, agrupar evidencia empírica y generar hipótesis de monetización.
  - 📄 Archivo clave: `repos/reddit-pain-research-skill/reddit-pain-research/SKILL.md`
  - 📄 Archivo clave: `repos/reddit-pain-research-skill/reddit-pain-research/scripts/build_reports.py`
  - 📄 Archivo clave: `repos/reddit-pain-research-skill/reddit-pain-research/scripts/create_research_config.py`

### Capa: Autonomous Lead Agents

- ✅ **MiloAgent** (`milo-agent`): Agente autónomo de crecimiento multi-comunidad con motor de investigación (`research_engine.py`) y hub de gestión de subreddits (`subreddit_hub.py`).
  - 📄 Archivo clave: `repos/milo-agent/miloagent.py`
  - 📄 Archivo clave: `repos/milo-agent/core/research_engine.py`
  - 📄 Archivo clave: `repos/milo-agent/core/subreddit_hub.py`

### Capa: Extraction & Scrapers

- ✅ **snscrape** (`snscrape`): Extracción sin autenticación vía protocolo público de Reddit (`snscrape/modules/reddit.py`), prescindiendo de credenciales y evitando bloqueos de API.
  - 📄 Archivo clave: `repos/snscrape/snscrape/modules/reddit.py`
  - 📄 Archivo clave: `repos/snscrape/snscrape/_cli.py`
  - 📄 Archivo clave: `repos/snscrape/snscrape/base.py`
- ✅ **Bellingcat Reddit Post Scraping Tool** (`bellingcat-reddit-post-scraping-tool`): Metodología OSINT forense para búsqueda de evidencia por palabras clave en Reddit con preservación estricta de marcas de tiempo UTC, IDs y metadatos de autor.
  - 📄 Archivo clave: `repos/bellingcat-reddit-post-scraping-tool/rpst/scraper.py`
  - 📄 Archivo clave: `repos/bellingcat-reddit-post-scraping-tool/rpst/api.py`
  - 📄 Archivo clave: `repos/bellingcat-reddit-post-scraping-tool/rpst/base.py`
- ✅ **Universal Reddit Scraper (URS)** (`urs-reddit-scraper`): CLI de scraping forense exhaustivo sin overhead, con soporte para recolección de comentarios anidados multinivel, feeds en vivo (Livestream) y perfiles en JSON/CSV.
  - 📄 Archivo clave: `repos/urs-reddit-scraper/urs/praw_scrapers/live_scrapers/Livestream.py`
  - 📄 Archivo clave: `repos/urs-reddit-scraper/urs/Urs.py`
  - 📄 Archivo clave: `repos/urs-reddit-scraper/urs/utils/DirInit.py`

### Capa: Knowledge Base & Strategy

- ✅ **Awesome AI Lead Generation** (`awesome-ai-lead-generation`): Directorio exhaustivo de herramientas, frameworks y arquitecturas probadas para generación de leads e identificación de intención comercial con IA.
  - 📄 Archivo clave: `repos/awesome-ai-lead-generation/README.md`
  - 📄 Archivo clave: `repos/awesome-ai-lead-generation/CONTRIBUTING.md`
- ✅ **Awesome Reddit Lead Gen** (`awesome-reddit-lead-gen`): Guía táctica de prospección comercial en Reddit: mapeo de subreddits de alto valor, plantillas de búsqueda booleana y reglas anti-baneo de la comunidad.
  - 📄 Archivo clave: `repos/awesome-reddit-lead-gen/README.md`

### Capa: Internal Architecture & Data Model

- ✅ **Reddit Core (Historical Monolith)** (`reddit-archive-core`): Código fuente original del backend de Reddit: controladores base, modelos de Thing/Account/Comment y algoritmos de búsqueda y ranking de subreddits.
  - 📄 Archivo clave: `repos/reddit-archive-core/r2/r2/controllers/reddit_base.py`
  - 📄 Archivo clave: `repos/reddit-archive-core/r2/r2/lib/subreddit_search.py`

### Capa: Extraction & API SDK

- ✅ **PRAW (Python Reddit API Wrapper)** (`praw`): SDK oficial y estándar industrial en Python: autenticación OAuth2 transparente, auto-throttling según rate limits oficiales de Reddit (60 req/min) y streams perezosos de posts y comentarios.
  - 📄 Archivo clave: `repos/praw/praw/reddit.py`
  - 📄 Archivo clave: `repos/praw/praw/models/listing/mixins/subreddit.py`
  - 📄 Archivo clave: `repos/praw/praw/models/reddit/comment.py`

### Capa: Extraction & Concurrency

- ✅ **Async PRAW** (`asyncpraw`): Implementación asíncrona de alto rendimiento construida sobre aiohttp y asyncio, diseñada para consumir streams de múltiples subreddits concurrentes sin bloquear el hilo principal.
  - 📄 Archivo clave: `repos/asyncpraw/asyncpraw/reddit.py`
  - 📄 Archivo clave: `repos/asyncpraw/asyncpraw/models/reddit/submission.py`
  - 📄 Archivo clave: `repos/asyncpraw/asyncpraw/models/auth.py`

### Capa: GTM & Buyer Language Extraction

- ✅ **reddit-find (GTM Buyer Language Miner)** `[LOTE 2]` (`reddit-find`): Extractor de investigación GTM que extrae frases reales de dolor de clientes ('buyer language'), menciones a la competencia y ángulos de contenido sin requerir API keys de Reddit, exportando Markdown estructurado optimizado para LLMs.
  - 📄 Archivo clave: `repos/reddit-find/README.md`
  - 📄 Archivo clave: `repos/reddit-find/reddit_find/cli.py`
  - 📄 Archivo clave: `repos/reddit-find/AGENTS.md`
  - 📄 Archivo clave: `repos/reddit-find/reddit_find/discover.py`

### Capa: LangGraph Autonomous Agents

- ✅ **Reddit Agent (LangGraph State Machine)** `[LOTE 2]` (`reddit-agent-langgraph`): Agente autónomo de engagement para Reddit implementado con LangGraph: orquesta una máquina de estados para descubrimiento de publicaciones emergentes, scoring de calidad con IA y aprobación humana (Human-in-the-Loop) vía Slack/Telegram.
  - 📄 Archivo clave: `repos/reddit-agent-langgraph/main.py`
  - 📄 Archivo clave: `repos/reddit-agent-langgraph/Reddit_Comment_Engagement_Agent_PRD_v2.1.md`
  - 📄 Archivo clave: `repos/reddit-agent-langgraph/agents/generator.py`
  - 📄 Archivo clave: `repos/reddit-agent-langgraph/agents/__init__.py`

### Capa: MCP & Semantic Discovery

- ✅ **Reddit Research MCP Server** `[LOTE 2]` (`reddit-research-mcp`): Servidor MCP (Model Context Protocol) que habilita búsqueda semántica sobre más de 20,000 subreddits, recuperación de hilos con citaciones verificadas y análisis competitivo asistido por IA para Claude Desktop, Cursor y Gemini.
  - 📄 Archivo clave: `repos/reddit-research-mcp/package.json`
  - 📄 Archivo clave: `repos/reddit-research-mcp/README.md`

### Capa: Visual Workflows & Automation

- ✅ **n8n Reddit Buying-Intent Scraper & Workflows** `[LOTE 2]` (`n8n-reddit-scraper`): Suite de workflows visuales listos para importar en n8n para capturar leads con intención de compra en Reddit, sincronizarlos a CRMs/Slack y conectarlos con agentes de IA vía protocolo MCP.
  - 📄 Archivo clave: `repos/n8n-reddit-scraper/README.md`
  - 📄 Archivo clave: `repos/n8n-reddit-scraper/mcp/claude-desktop.json`
  - 📄 Archivo clave: `repos/n8n-reddit-scraper/mcp/cursor.json`
  - 📄 Archivo clave: `repos/n8n-reddit-scraper/mcp/README.md`

### Capa: Big Data Streaming & Distributed Processing

- ✅ **Reddit Real-Time Streaming Big Data Pipeline** `[LOTE 2]` (`reddit-streaming-pipeline`): Arquitectura de streaming distribuido a gran escala: consume comentarios continuos de Reddit vía Kafka, los procesa y agrega en tiempo real con Apache Spark Streaming, los persiste en Cassandra y los visualiza en Grafana.
  - 📄 Archivo clave: `repos/reddit-streaming-pipeline/README.md`
  - 📄 Archivo clave: `repos/reddit-streaming-pipeline/reddit_producer/reddit_producer.py`
  - 📄 Archivo clave: `repos/reddit-streaming-pipeline/images/Reddit Sentiment Analysis Data Pipeline.drawio.png`
  - 📄 Archivo clave: `repos/reddit-streaming-pipeline/images/top_subreddit_panel.png`

### Capa: Full-Stack Sentiment Platforms

- ✅ **Reddit Sentiment Analysis Platform (React + Flask)** `[LOTE 2]` (`reddit-sentiment-analysis-fullstack`): Plataforma full-stack desacoplada (Frontend React + Backend Flask) con clasificadores de Machine Learning entrenados para predecir polaridad de hilos y generar reportes gráficos de percepción de marca.
  - 📄 Archivo clave: `repos/reddit-sentiment-analysis-fullstack/README.md`
  - 📄 Archivo clave: `repos/reddit-sentiment-analysis-fullstack/sentiment_analysis_backend/app.py`
  - 📄 Archivo clave: `repos/reddit-sentiment-analysis-fullstack/sentiment_analysis_backend/app_launcher/run_app.py`
  - 📄 Archivo clave: `repos/reddit-sentiment-analysis-fullstack/sentiment_analysis_backend/app.log`

### Capa: ChromaDB & Knowledge Management

- ✅ **Reddit Knowledge Base MCP Server (ChromaDB)** `[LOTE 2]` (`reddit-kb-mcp-server`): Servidor MCP que convierte el archivo y guardados de Reddit en una base de conocimiento vectorial indexada en ChromaDB, permitiendo a asistentes de IA realizar consultas semánticas y RAG sobre hilos complejos.
  - 📄 Archivo clave: `repos/reddit-kb-mcp-server/server.py`
  - 📄 Archivo clave: `repos/reddit-kb-mcp-server/requirements.txt`
  - 📄 Archivo clave: `repos/reddit-kb-mcp-server/README.md`

### Capa: Qdrant & Multimodal Search

- ✅ **Multimodal Reddit Search (CLIP + Qdrant)** `[LOTE 2]` (`multimodal-reddit-search`): Motor de búsqueda vectorial multimodal que ingesta posts de Reddit, genera representaciones vectoriales conjuntas de texto e imágenes mediante OpenAI CLIP y las indexa en Qdrant para búsquedas cruzadas texto-imagen.
  - 📄 Archivo clave: `repos/multimodal-reddit-search/README.md`
  - 📄 Archivo clave: `repos/multimodal-reddit-search/fetch_reddit_posts.py`
  - 📄 Archivo clave: `repos/multimodal-reddit-search/main.py`
  - 📄 Archivo clave: `repos/multimodal-reddit-search/streamlit_app.py`

### Capa: Zero-Shot NLP Classification

- ✅ **Reddit Sentiment Zero-Shot NLI Pipeline** `[LOTE 2]` (`reddit-sentiment-zero-shot`): Pipeline de investigación en NLP para clasificar hilos de discusión de Reddit usando modelos Zero-Shot basados en Inferencia de Lenguaje Natural (NLI), permitiendo categorizar quejas e intenciones sin requerir datos etiquetados previos.
  - 📄 Archivo clave: `repos/reddit-sentiment-zero-shot/README.md`
  - 📄 Archivo clave: `repos/reddit-sentiment-zero-shot/data/amazon_sentiment_series.json`
  - 📄 Archivo clave: `repos/reddit-sentiment-zero-shot/data/apple_sentiment_series.json`
  - 📄 Archivo clave: `repos/reddit-sentiment-zero-shot/data/google_sentiment_series.json`

### Capa: Playwright Browser Automation

- ✅ **Reddit Hole (Playwright Headless Automation)** `[LOTE 2]` (`reddit-hole-playwright`): Crawler headless basado en Playwright para sortear protecciones de renderizado dinámico en JavaScript de Reddit, emular interacciones humanas y extraer posts y metadatos sin depender del API oficial.
  - 📄 Archivo clave: `repos/reddit-hole-playwright/main.py`
  - 📄 Archivo clave: `repos/reddit-hole-playwright/utils/reddit.py`
  - 📄 Archivo clave: `repos/reddit-hole-playwright/docs/reddit-banner.png`
  - 📄 Archivo clave: `repos/reddit-hole-playwright/docs/reddit1.png`

### Capa: LanceDB Serverless Vectors

- ✅ **LanceDB Serverless Vector Storage Recipes** `[LOTE 2]` (`lancedb-vectordb-recipes`): Patrones de diseño de LanceDB para almacenamiento vectorial serverless en disco (formato columnar Lance) con pipelines de RAG y clustering de baja latencia sobre posts y comentarios de Reddit sin costo de servidor.
  - 📄 Archivo clave: `repos/lancedb-vectordb-recipes/examples/`
  - 📄 Archivo clave: `repos/lancedb-vectordb-recipes/tutorials/`
  - 📄 Archivo clave: `repos/lancedb-vectordb-recipes/README.md`

### Capa: Qdrant Hybrid Search & Memory

- ✅ **VectFox (Qdrant Hybrid Search & RAG Memory)** `[LOTE 2]` (`vectfox-hybrid-search`): Sistema de memoria RAG y búsqueda híbrida (embeddings densos + léxico disperso) implementado sobre la base de datos vectorial Qdrant para recuperación contextual y summarization de discusiones extensas de Reddit.
  - 📄 Archivo clave: `repos/vectfox-hybrid-search/README.md`
  - 📄 Archivo clave: `repos/vectfox-hybrid-search/.mcp.json`
  - 📄 Archivo clave: `repos/vectfox-hybrid-search/core/agentic-retrieval.js`
  - 📄 Archivo clave: `repos/vectfox-hybrid-search/core/eventbase-extractor.js`

---

## 4. Matriz de Síntesis para Arquitectura Micro-SaaS

Con la incorporación del Lote 2, el flujo de desarrollo de un validador rápido de Micro-SaaS cuenta ahora con alternativas especializadas por capa:

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

---
*Catálogo maestro actualizado con 57 repositorios por el orquestador Reddit Intelligence Radar.*
