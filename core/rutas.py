"""
Dónde está el código del motor y dónde están los datos (AUD2-003, DP1 B)
======================================================================

La release lanza el motor desde una copia versionada de su código, fuera del
repositorio; los datos del proyecto (el `.env`, los vectores de LanceDB)
siguen en la carpeta del proyecto y los comparten todas las versiones. Por
eso ninguna ruta de datos puede salir de `__file__`: en la copia apuntaría
dentro de ella. La aplicación pasa la carpeta del proyecto en
`RIR_DATA_DIR`; sin ella (desarrollo y tests) los datos están junto al
código, como siempre.
"""

from __future__ import annotations

import functools
import os
from collections.abc import Iterable
from pathlib import Path

DATA_DIR_ENV_VAR = "RIR_DATA_DIR"
MODELS_DIR_ENV_VAR = "RIR_MODELS_DIR"
#: La aplicación la pone a "1" al lanzar el motor desde su copia versionada.
VERSIONADO_ENV_VAR = "RIR_MOTOR_VERSIONADO"

_FNV_BASE = 0xCBF29CE484222325
_FNV_PRIMO = 0x100000001B3
_MASCARA = 0xFFFFFFFFFFFFFFFF

#: <raíz>/core/rutas.py → la raíz del código del motor (repo o copia versionada).
RAIZ_CODIGO = Path(__file__).resolve().parents[1]


def raiz_datos() -> Path:
    """Carpeta del proyecto con el `.env` y `data/`."""
    valor = os.environ.get(DATA_DIR_ENV_VAR, "").strip()
    return Path(valor) if valor else RAIZ_CODIGO


def carpeta_local() -> Path:
    """Carpeta local de SENTRA fuera del repositorio: %LOCALAPPDATA%/SENTRA,
    o ~/.cache/sentra sin esa variable."""
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        return Path(local) / "SENTRA"
    return Path.home() / ".cache" / "sentra"


def ruta_modelos() -> Path:
    """Caché de los modelos de embeddings (AUD2-010, DP9 A): fuera de %TEMP%,
    donde una limpieza de temporales se llevaba los 2,1 GB de e5."""
    explicita = os.environ.get(MODELS_DIR_ENV_VAR, "").strip()
    return Path(explicita) if explicita else carpeta_local() / "models"


def ruta_pgpass() -> Path:
    """Contraseñas de los roles de SENTRA (sentra_owner, sentra_pruebas): propias,
    fuera del pgpass.conf que comparten los proyectos de la máquina. Rust usa la
    misma ruta (ui/src-tauri/src/db.rs, ruta_pgpass)."""
    return carpeta_local() / "pgpass.conf"


def ruta_cache_modelos_gemini() -> Path:
    """Lista de modelos de Gemini entre arranques (AUD2-019)."""
    return carpeta_local() / "cache" / "gemini_models.json"


def fnv1a64(datos: bytes) -> str:
    """FNV-1a de 64 bits en hexadecimal. Huella, no seguridad: detecta que el
    código del motor no es el que se compiló con la interfaz."""
    h = _FNV_BASE
    for byte in datos:
        h = ((h ^ byte) * _FNV_PRIMO) & _MASCARA
    return f"{h:016x}"


def huella(ficheros: Iterable[tuple[str, bytes]]) -> str:
    """Huella de un conjunto de ficheros: por ruta ordenada, `ruta\0longitud\0contenido`.

    La misma composición la calcula build.rs al empaquetar el motor.
    """
    partes = bytearray()
    for ruta, contenido in sorted(ficheros):
        partes += ruta.encode("utf-8") + b"\0" + str(len(contenido)).encode() + b"\0" + contenido
    return fnv1a64(bytes(partes))


def huella_de_carpeta(raiz: Path) -> str:
    """Huella de todo lo que hay bajo `raiz`, salvo la caché de Python y los
    marcadores (ficheros que empiezan por punto)."""
    ficheros = [
        (p.relative_to(raiz).as_posix(), p.read_bytes())
        for p in raiz.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and not p.name.startswith(".")
    ]
    return huella(ficheros)


@functools.cache
def huella_del_motor() -> str | None:
    """Huella del código que corre, solo en la copia versionada: en el repo
    (desarrollo, tests) la carpeta tiene de todo y no hay nada que comparar."""
    if os.environ.get(VERSIONADO_ENV_VAR, "").strip() != "1":
        return None
    return huella_de_carpeta(RAIZ_CODIGO)
