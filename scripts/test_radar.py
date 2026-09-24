#!/usr/bin/env python3
"""
Suite de Pruebas y Verificacion TDD para SENTRA
Valida la integridad de los repositorios descargados, consistencia del catalogo
y conformidad del archivo maestro INDEX.md con las reglas establecidas.
"""

import json
import sys
from pathlib import Path

# La raíz del repositorio, desde aquí: funciona en cualquier unidad y copia (D5).
BASE_DIR = Path(__file__).resolve().parents[1]
REPOS_DIR = BASE_DIR / "repos"
LOGS_DIR = BASE_DIR / "logs"
RESULTS_FILE = LOGS_DIR / "clone_results.json"
CATALOG_FILE = LOGS_DIR / "repo_catalog.json"
INDEX_FILE = BASE_DIR / "INDEX.md"

def test_radar():
    print("=== INICIANDO SUITE DE PRUEBAS DE VERIFICACION ===")
    errors = []
    passes = 0

    # Test 1: Verificar existencia del archivo de resultados de clonacion
    if not RESULTS_FILE.exists():
        errors.append(f"[FALLO] No existe archivo de resultados: {RESULTS_FILE}")
    else:
        passes += 1
        print(f"[PASS] Archivo de resultados de clonacion presente: {RESULTS_FILE.name}")

    # Test 2: Verificar contenido de repositorios en disco
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            results = json.load(f)

        successful_clones = [r for r in results if r.get("status") == "success"]
        print(f"Total repositorios procesados: {len(results)}, Exitosos: {len(successful_clones)}")

        for r in successful_clones:
            folder = Path(r["folder"])
            if not folder.exists():
                errors.append(f"[FALLO] La carpeta {folder} no existe en disco.")
            else:
                # Verificar que tenga archivos reales
                files = list(folder.glob("*"))
                if not files:
                    errors.append(f"[FALLO] La carpeta {folder} esta vacia.")
                else:
                    passes += 1

    # Test 3: Verificar archivo maestro INDEX.md
    if not INDEX_FILE.exists():
        errors.append(f"[FALLO] No existe el archivo maestro INDEX.md: {INDEX_FILE}")
    else:
        passes += 1
        print("[PASS] Archivo maestro INDEX.md presente.")
        content = INDEX_FILE.read_text(encoding="utf-8")
        
        # Verificar columnas obligatorias
        required_headers = [
            "Nombre del Proyecto",
            "URL",
            "Técnica Única que Aporta",
            "Archivos/Módulos Clave para Estudiar"
        ]
        for header in required_headers:
            if header not in content:
                errors.append(f"[FALLO] Columna requerida ausente en INDEX.md: '{header}'")
            else:
                passes += 1
                print(f"[PASS] Columna verificada en INDEX.md: '{header}'")

    # Test 4: Verificar rutas de archivos clave en repo_catalog.json
    if CATALOG_FILE.exists():
        with open(CATALOG_FILE, "r", encoding="utf-8") as f:
            catalog = json.load(f)

        for entry in catalog:
            if entry.get("status") == "ready":
                repo_path = Path(entry["local_path"])
                key_files = entry.get("key_files", [])
                if not key_files:
                    errors.append(f"[FALLO] No se detectaron archivos clave para {entry['name']}")
                else:
                    passes += 1
                    # Verificar que al menos un archivo clave exista fisicamente
                    exists_any = any((repo_path / kf).exists() for kf in key_files)
                    if not exists_any:
                        errors.append(f"[FALLO] Ninguno de los archivos clave existe fisicamente en {repo_path}")
                    else:
                        passes += 1

    print("\n" + "=" * 50)
    print(f"RESULTADO DE LAS PRUEBAS: {passes} PASADAS | {len(errors)} FALLADAS")
    if errors:
        print("\nDETALLE DE FALLOS:")
        for err in errors:
            print(f" - {err}")
        print("=" * 50)
        return False
    else:
        print("TODAS LAS PRUEBAS COMPLETADAS SATISFACTORIAMENTE (GREEN).")
        print("=" * 50)
        return True

if __name__ == "__main__":
    success = test_radar()
    sys.exit(0 if success else 1)
