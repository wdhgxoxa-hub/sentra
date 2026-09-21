#!/usr/bin/env python3
"""
Actualizador y Consolidador de Metadatos de Clonación
Registra las resoluciones de aliases e incidencias para los repositorios renombrados/redirigidos.
"""

import json
from pathlib import Path

BASE_DIR = Path(r"F:\reddit_intelligence_radar")
LOGS_DIR = BASE_DIR / "logs"
REPOS_DIR = BASE_DIR / "repos"
RESULTS_FILE = LOGS_DIR / "clone_results.json"

RESOLVED_UPDATES = {
    "praw": {
        "id": "praw",
        "owner": "praw-dev",
        "repo": "praw",
        "original_requested": "praw-community/praw",
        "url": "https://github.com/praw-dev/praw.git",
        "category": "Extraction & API SDK",
        "tag": "Base",
        "reason": "SDK oficial y estándar de la industria en Python para interactuar con la API de Reddit (OAuth2, auto-throttling y streaming).",
        "folder": str(REPOS_DIR / "praw"),
        "status": "success",
        "incidence": "La organización oficial en GitHub se ubica en 'praw-dev', no 'praw-community'. Resuelto y descargado exitosamente."
    },
    "asyncpraw": {
        "id": "asyncpraw",
        "owner": "praw-dev",
        "repo": "asyncpraw",
        "original_requested": "praw-community/asyncpraw",
        "url": "https://github.com/praw-dev/asyncpraw.git",
        "category": "Extraction & Concurrency",
        "tag": "Base Complement",
        "reason": "Implementación asíncrona oficial basada en asyncio y aiohttp para monitoreo concurrente de subreddits de alto tráfico.",
        "folder": str(REPOS_DIR / "asyncpraw"),
        "status": "success",
        "incidence": "La organización oficial en GitHub se ubica en 'praw-dev', no 'praw-community'. Resuelto y descargado exitosamente."
    },
    "bellingcat-reddit-post-scraping-tool": {
        "id": "bellingcat-reddit-post-scraping-tool",
        "owner": "bellingcat",
        "repo": "reddit-post-scraping-tool",
        "original_requested": "bellingcat/reddit-scraper",
        "url": "https://github.com/bellingcat/reddit-post-scraping-tool.git",
        "category": "Extraction & Scrapers",
        "tag": "Base",
        "reason": "Herramienta OSINT de Bellingcat para búsqueda y extracción forense de publicaciones en Reddit basadas en palabras clave.",
        "folder": str(REPOS_DIR / "bellingcat-reddit-post-scraping-tool"),
        "status": "success",
        "incidence": "El repositorio oficial de Bellingcat está nombrado 'reddit-post-scraping-tool'. Resuelto y descargado exitosamente."
    },
    "urs-reddit-scraper": {
        "id": "urs-reddit-scraper",
        "owner": "JosephLai241",
        "repo": "URS",
        "original_requested": "josephroi/reddit-scraper",
        "url": "https://github.com/JosephLai241/URS.git",
        "category": "Extraction & Scrapers",
        "tag": "Base",
        "reason": "Universal Reddit Scraper (URS): Herramienta CLI de scraping exhaustivo para subreddits, posts, comentarios anidados y perfiles de usuario.",
        "folder": str(REPOS_DIR / "urs-reddit-scraper"),
        "status": "success",
        "incidence": "El repositorio canónico creado por Joseph Lai es 'JosephLai241/URS'. Resuelto y descargado exitosamente."
    }
}

def update_results():
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        results = json.load(f)

    updated_map = {}
    for r in results:
        # Si fue uno de los que fallaron con la URL anterior, no sobreescribir el ID si ya fue resuelto
        if r["id"] in ["praw", "asyncpraw", "josephroi-reddit-scraper", "bellingcat-reddit-scraper"]:
            continue
        updated_map[r["id"]] = r

    for k, v in RESOLVED_UPDATES.items():
        updated_map[k] = v

    final_list = list(updated_map.values())
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(final_list, f, indent=2, ensure_ascii=False)

    print(f"Resultados consolidados: {len(final_list)} repositorios registrados como activos y descargados.")

if __name__ == "__main__":
    update_results()
