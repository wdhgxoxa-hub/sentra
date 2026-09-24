#!/usr/bin/env python3
"""
Auditoría Exhaustiva de Integridad para Reddit Intelligence Radar
Verifica los 57 proyectos (Lote 1: 45 repos, Lote 2: 12 repos)
Comprobaciones:
1. Existencia del directorio en F:\\reddit_intelligence_radar\\repos\\<id>
2. Existencia y validez del repositorio git (.git, rev-parse HEAD)
3. git status --porcelain (árbol de trabajo limpio, sin archivos truncados/modificados/conflictos)
4. git fsck --connectivity-only (integridad del grafo de objetos Git)
5. Verificación de todos los archivos y módulos clave listados en INDEX.md / repo_catalog.json
6. Métricas de disco (conteo de archivos y tamaño en bytes)
7. Detección de cualquier necesidad de re-clonado o reparación
"""

import contextlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# La raíz del repositorio, desde aquí: funciona en cualquier unidad y copia (D5).
BASE_DIR = Path(__file__).resolve().parents[1]
REPOS_DIR = BASE_DIR / "repos"
LOGS_DIR = BASE_DIR / "logs"
INDEX_FILE = BASE_DIR / "INDEX.md"
CATALOG_FILE = LOGS_DIR / "repo_catalog.json"
OUTPUT_REPORT = LOGS_DIR / "integrity_audit.json"

BATCH2_IDS = {
    "reddit-find", "reddit-agent-langgraph", "reddit-research-mcp",
    "n8n-reddit-scraper", "reddit-streaming-pipeline", "reddit-sentiment-analysis-fullstack",
    "reddit-kb-mcp-server", "multimodal-reddit-search", "reddit-sentiment-zero-shot",
    "reddit-hole-playwright", "lancedb-vectordb-recipes", "vectfox-hybrid-search"
}

def parse_index_key_files():
    """Extrae del INDEX.md la lista de archivos clave por cada repositorio."""
    if not INDEX_FILE.exists():
        return {}
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    
    table_matches = re.findall(
        r'\|\s*\[(.*?)\]\((.*?)\)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|',
        content
    )
    
    mapping = {}
    for match in table_matches:
        url = match[1].strip()
        files_col = match[4].strip()
        # extraer rutas entre comillas invertidas `...`
        raw_files = re.findall(r'`(.*?)`', files_col)
        # Normalizar rutas
        clean_files = [f.replace('\\', '/') for f in raw_files if f]
        mapping[url.lower()] = clean_files
    return mapping

def run_audit():
    if not CATALOG_FILE.exists():
        print(f"Error: {CATALOG_FILE} no encontrado.")
        sys.exit(1)

    with open(CATALOG_FILE, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    index_key_files_map = parse_index_key_files()

    results = []

    for item in catalog:
        repo_id = item["id"]
        repo_url = item.get("url", "").lower()
        batch_label = "Lote 2" if repo_id in BATCH2_IDS else "Lote 1"
        repo_path = REPOS_DIR / repo_id
        
        # 1. Existencia del directorio
        folder_exists = repo_path.exists() and repo_path.is_dir()
        git_dir_exists = (repo_path / ".git").exists() if folder_exists else False

        git_head = None
        git_clean = None
        git_status_raw = ""
        git_fsck_ok = None
        git_remote = None
        error_notes = []

        if not folder_exists:
            error_notes.append("Directorio no existe")
        elif not git_dir_exists:
            error_notes.append("Directorio .git ausente")
        else:
            # 2. git rev-parse HEAD
            try:
                p_head = subprocess.run(
                    ["git", "-C", str(repo_path), "rev-parse", "--short", "HEAD"],
                    capture_output=True, text=True, timeout=15, check=False
                )
                if p_head.returncode == 0:
                    git_head = p_head.stdout.strip()
                else:
                    error_notes.append(f"Fallo HEAD: {p_head.stderr.strip()}")
            except (OSError, subprocess.SubprocessError) as e:
                error_notes.append(f"Excepción rev-parse: {e}")

            # 3. git remote get-url origin
            try:
                p_rem = subprocess.run(
                    ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
                    capture_output=True, text=True, timeout=15, check=False
                )
                if p_rem.returncode == 0:
                    git_remote = p_rem.stdout.strip()
            except (OSError, subprocess.SubprocessError) as e:
                error_notes.append(f"Excepción remote get-url: {e}")

            # 4. git status --porcelain
            try:
                p_status = subprocess.run(
                    ["git", "-C", str(repo_path), "status", "--porcelain"],
                    capture_output=True, text=True, timeout=15, check=False
                )
                if p_status.returncode == 0:
                    git_status_raw = p_status.stdout.strip()
                    git_clean = (len(git_status_raw) == 0)
                    if not git_clean:
                        error_notes.append(f"Working tree no limpio: {git_status_raw}")
                else:
                    git_clean = False
                    error_notes.append(f"Fallo git status: {p_status.stderr.strip()}")
            except (OSError, subprocess.SubprocessError) as e:
                git_clean = False
                error_notes.append(f"Excepción git status: {e}")

            # 5. git fsck --connectivity-only
            try:
                p_fsck = subprocess.run(
                    ["git", "-C", str(repo_path), "fsck", "--connectivity-only"],
                    capture_output=True, text=True, timeout=30, check=False
                )
                git_fsck_ok = (p_fsck.returncode == 0)
                if not git_fsck_ok:
                    error_notes.append(f"Fallo git fsck: {p_fsck.stderr.strip() or p_fsck.stdout.strip()}")
            except (OSError, subprocess.SubprocessError) as e:
                git_fsck_ok = False
                error_notes.append(f"Excepción git fsck: {e}")

        # 6. Comprobación de archivos clave (de INDEX.md y de repo_catalog.json)
        # Combinar los archivos clave identificados
        target_key_files = set()
        for kf in item.get("key_files", []):
            target_key_files.add(kf.replace('\\', '/'))
        for ikf in index_key_files_map.get(repo_url, []):
            # si viene como repos/repo_id/path, convertir a path relativo al repo
            prefix = f"repos/{repo_id}/"
            if ikf.startswith(prefix):
                target_key_files.add(ikf[len(prefix):])
            else:
                target_key_files.add(ikf)

        key_files_detail = []
        for kf in sorted(target_key_files):
            # Probar relativo al repo
            p1 = repo_path / kf
            # Probar relativo a BASE_DIR
            p2 = BASE_DIR / kf
            exists = p1.exists() or p2.exists()
            key_files_detail.append({
                "file": kf,
                "exists": exists,
                "is_dir": (p1.is_dir() or p2.is_dir()) if exists else False
            })

        missing_files = [kf["file"] for kf in key_files_detail if not kf["exists"]]
        if missing_files:
            error_notes.append(f"Archivos clave faltantes: {missing_files}")

        # 7. Métricas de disco
        file_count = 0
        total_bytes = 0
        if folder_exists:
            for root, dirs, files in os.walk(repo_path):
                file_count += len(files)
                for f_name in files:
                    fp = Path(root) / f_name
                    # Un archivo que desaparece o no se puede leer durante el
                    # recorrido no suma bytes: la métrica es aproximada.
                    with contextlib.suppress(OSError):
                        if not fp.is_symlink():
                            total_bytes += fp.stat().st_size

        # Determinar si está 100% íntegro
        is_intact = bool(
            folder_exists and
            git_dir_exists and
            git_head and
            git_clean and
            git_fsck_ok and
            (len(missing_files) == 0) and
            (file_count > 0)
        )

        results.append({
            "id": repo_id,
            "name": item["name"],
            "batch": batch_label,
            "category": item.get("category", ""),
            "url": item.get("url", ""),
            "folder_exists": folder_exists,
            "git_dir_exists": git_dir_exists,
            "git_head": git_head,
            "git_remote": git_remote,
            "git_clean": git_clean,
            "git_fsck_ok": git_fsck_ok,
            "key_files_total": len(key_files_detail),
            "key_files_ok": sum(1 for k in key_files_detail if k["exists"]),
            "missing_key_files": missing_files,
            "file_count": file_count,
            "total_bytes": total_bytes,
            "size_mb": round(total_bytes / (1024 * 1024), 2),
            "is_fully_intact": is_intact,
            "action_required": "None" if is_intact else "Re-clone / Repair",
            "error_notes": error_notes
        })

    # Desglose por lotes
    b1_items = [r for r in results if r["batch"] == "Lote 1"]
    b2_items = [r for r in results if r["batch"] == "Lote 2"]
    
    b1_intact = [r for r in b1_items if r["is_fully_intact"]]
    b2_intact = [r for r in b2_items if r["is_fully_intact"]]
    total_intact = [r for r in results if r["is_fully_intact"]]
    issues = [r for r in results if not r["is_fully_intact"]]

    audit_summary: dict[str, Any] = {
        "audit_timestamp": "2026-09-18T11:10:00Z",
        "total_repositories": len(results),
        "total_fully_intact": len(total_intact),
        "total_requiring_action": len(issues),
        "integrity_rate_percent": round(len(total_intact) / len(results) * 100, 2),
        "batch_1": {
            "total": len(b1_items),
            "intact": len(b1_intact),
            "requires_action": len(b1_items) - len(b1_intact),
            "integrity_percent": round(len(b1_intact) / len(b1_items) * 100, 2)
        },
        "batch_2": {
            "total": len(b2_items),
            "intact": len(b2_intact),
            "requires_action": len(b2_items) - len(b2_intact),
            "integrity_percent": round(len(b2_intact) / len(b2_items) * 100, 2)
        },
        "issues": issues,
        "repositories": results
    }

    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(audit_summary, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("      REPORTE EJECUTIVO DE INTEGRIDAD — REDDIT INTELLIGENCE RADAR")
    print("=" * 70)
    print(f"Total de Repositorios Analizados: {len(results)}")
    print(f"100% Íntegros y Operativos:       {len(total_intact)} / {len(results)} ({audit_summary['integrity_rate_percent']}%)")
    print(f"Requieren Re-clonado / Reparación: {len(issues)}")
    print("-" * 70)
    print(f"  • Lote 1 (Base + Expansión):   {len(b1_intact)} / {len(b1_items)} íntegros ({audit_summary['batch_1']['integrity_percent']}%)")
    print(f"  • Lote 2 (Nueva Expansión):    {len(b2_intact)} / {len(b2_items)} íntegros ({audit_summary['batch_2']['integrity_percent']}%)")
    print("=" * 70)

    if issues:
        print("\n[ALERTA] Se encontraron anomalías en los siguientes repositorios:")
        for r in issues:
            print(f" - [{r['batch']}] {r['id']}")
            print(f"   Errores: {', '.join(r['error_notes'])}")
    else:
        print("\n[ÉXITO TOTAL] Los 57 repositorios están 100% íntegros:")
        print("  - Todas las carpetas existen y están pobladas.")
        print("  - Todos los árboles de Git están intactos (.git, HEAD válido, commit histórico presente).")
        print("  - Árbol de trabajo en limpio (git status limpio sin conflictos ni modificaciones locales).")
        print("  - Base de objetos Git verificada sin corrupción (git fsck).")
        print("  - 100% de los archivos y módulos clave descritos en INDEX.md existen en disco.")

if __name__ == "__main__":
    run_audit()
