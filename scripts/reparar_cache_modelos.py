"""
Repara la caché de modelos de fastembed traída de Windows
=========================================================

fastembed 0.8.0 guarda junto a cada modelo un `files_metadata.json` con la ruta
relativa y el tamaño de cada archivo. En Windows lo escribió con «\\»
(`snapshots\\<revisión>\\config.json`); en Linux esa ruta es un solo nombre que
no existe, así que en cada carga avisaba «Local file sizes do not match the
metadata» aunque los archivos estuvieran enteros (2026-10-12).

Este script no descarga nada ni cambia ningún modelo. Para cada
`models--*` de la caché (`core.rutas.ruta_modelos()`):

1. Comprueba cada archivo de `snapshots/<revisión>/` contra el árbol que
   guardó huggingface_hub (`trees/<revisión>.json`): tamaño y, si el árbol lo
   trae, sha256 (archivos grandes) o el identificador de git (los pequeños).
2. Si todo cuadra y el `files_metadata.json` tiene rutas de Windows, escribe
   uno nuevo con las mismas entradas y rutas con «/». El viejo va a la
   papelera (`gio trash`); sin `gio`, se queda al lado como `.windows`.
3. Si algún archivo no cuadra, no toca nada y lo dice: hay que volver a
   descargar ese modelo.

Uso
---
    python -m scripts.reparar_cache_modelos --en-seco   # dice qué haría
    python -m scripts.reparar_cache_modelos             # lo hace
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

METADATOS = "files_metadata.json"
_BLOQUE = 1 << 20


@dataclass
class Resultado:
    modelo: str
    estado: str  # «bien», «reparable», «reparado», «dañado», «sin metadatos»
    detalles: list[str] = field(default_factory=list)


def ruta_posix(clave: str) -> str:
    """`snapshots\\abc\\config.json` → `snapshots/abc/config.json` (las de Linux no cambian)."""
    return PureWindowsPath(clave).as_posix() if "\\" in clave else clave


def huella(archivo: Path, sha256: bool) -> str:
    """sha256 del contenido, o el identificador de git del blob (sha1 de «blob <n>\\0» + contenido)."""
    if sha256:
        calculo = hashlib.sha256()
    else:
        calculo = hashlib.sha1(usedforsecurity=False)  # el identificador de git
        calculo.update(f"blob {archivo.stat().st_size}\0".encode())
    with archivo.open("rb") as f:
        while bloque := f.read(_BLOQUE):
            calculo.update(bloque)
    return calculo.hexdigest()


def comprobar_archivos(carpeta: Path) -> list[str]:
    """Problemas de los archivos de las instantáneas frente al árbol guardado (vacía = todo bien)."""
    problemas: list[str] = []
    for instantanea in sorted((carpeta / "snapshots").glob("*")):
        arbol_json = carpeta / "trees" / f"{instantanea.name}.json"
        if not arbol_json.is_file():
            problemas.append(f"falta el árbol {arbol_json.name}: no se puede comprobar")
            continue
        arbol = json.loads(arbol_json.read_text(encoding="utf-8"))["files"]
        for archivo in sorted(p for p in instantanea.rglob("*") if p.is_file()):
            relativa = archivo.relative_to(instantanea).as_posix()
            esperado = arbol.get(relativa)
            if esperado is None:
                problemas.append(f"{relativa}: no está en el árbol del repositorio")
                continue
            if archivo.stat().st_size != esperado["size"]:
                problemas.append(f"{relativa}: mide {archivo.stat().st_size}, "
                                 f"debería medir {esperado['size']}")
                continue
            if "lfs_sha256" in esperado:
                if huella(archivo, sha256=True) != esperado["lfs_sha256"]:
                    problemas.append(f"{relativa}: el sha256 no cuadra")
            elif huella(archivo, sha256=False) != esperado["blob_id"]:
                problemas.append(f"{relativa}: el identificador de git no cuadra")
    return problemas


def a_la_papelera(archivo: Path) -> str:
    """`gio trash`; sin gio (Windows, macOS), lo deja al lado como `.windows`."""
    gio = shutil.which("gio")
    if gio:
        subprocess.run([gio, "trash", str(archivo)], check=True)
        return "a la papelera"
    respaldo = archivo.with_name(archivo.name + ".windows")
    os.replace(archivo, respaldo)
    return f"guardado como {respaldo.name}"


def revisar_modelo(carpeta: Path, aplicar: bool,
                   papelera: Callable[[Path], str] = a_la_papelera) -> Resultado:
    metadatos_json = carpeta / METADATOS
    if not metadatos_json.is_file():
        return Resultado(carpeta.name, "sin metadatos")
    metadatos = json.loads(metadatos_json.read_text(encoding="utf-8"))
    nuevos = {ruta_posix(clave): valor for clave, valor in metadatos.items()}
    problemas = comprobar_archivos(carpeta)
    for clave, valor in nuevos.items():
        archivo = carpeta / clave
        if not archivo.is_file():
            problemas.append(f"{clave}: está en {METADATOS} pero no existe")
        elif archivo.stat().st_size != valor["size"]:
            problemas.append(f"{clave}: {METADATOS} dice {valor['size']} bytes")
    if problemas:
        return Resultado(carpeta.name, "dañado", problemas)
    if nuevos == metadatos:
        return Resultado(carpeta.name, "bien")
    cambios = [f"{a} → {b}" for a, b in zip(metadatos, nuevos) if a != b]
    if not aplicar:
        return Resultado(carpeta.name, "reparable", cambios)
    temporal = metadatos_json.with_name(METADATOS + ".nuevo")
    temporal.write_text(json.dumps(nuevos), encoding="utf-8")
    destino_viejo = papelera(metadatos_json)
    os.replace(temporal, metadatos_json)
    return Resultado(carpeta.name, "reparado", [f"el viejo, {destino_viejo}", *cambios])


def revisar(cache: Path, aplicar: bool,
            papelera: Callable[[Path], str] = a_la_papelera) -> list[Resultado]:
    return [revisar_modelo(c, aplicar, papelera) for c in sorted(cache.glob("models--*"))
            if c.is_dir()]


def main(argv: Sequence[str] | None = None) -> int:
    from core.rutas import ruta_modelos

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--en-seco", action="store_true", help="solo dice qué haría")
    parser.add_argument("--cache", type=Path, default=None,
                        help="carpeta de modelos (por defecto, la de SENTRA)")
    args = parser.parse_args(argv)
    cache = args.cache or ruta_modelos()
    resultados = revisar(cache, aplicar=not args.en_seco)
    print(f"Caché de modelos: {cache}")
    for r in resultados:
        print(f"- {r.modelo}: {r.estado}")
        for detalle in r.detalles:
            print(f"    {detalle}")
    if not resultados:
        print("- no hay modelos")
    return 1 if any(r.estado == "dañado" for r in resultados) else 0


if __name__ == "__main__":
    sys.exit(main())
