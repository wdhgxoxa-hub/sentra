"""
El archivo .env del proyecto: escritura atómica
===============================================

Guarda las credenciales de todas las fuentes y la sal de los autores. Se
reescribe entero en un temporal de la misma carpeta y se sustituye con
`os.replace`, que es atómico: si el proceso muere a mitad, queda el archivo
anterior, nunca uno truncado sin claves. Se reescribe en lugar de anexar:
anexar dejaría duplicados y la última línea ganaría en silencio.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def default_env_path() -> str:
    """Ruta del `.env` del proyecto."""
    return str(Path(__file__).resolve().parents[1] / ".env")


def update_dotenv(values: dict[str, str], path: str | None = None) -> Path:
    """Escribe o actualiza claves en un `.env`, preservando el resto."""
    target = Path(path or default_env_path())
    target.parent.mkdir(parents=True, exist_ok=True)

    lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    pending = dict(values)
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in pending:
                result.append(f"{key}={pending.pop(key)}")
                continue
        result.append(line)
    result.extend(f"{key}={value}" for key, value in pending.items())

    descriptor, temporal = tempfile.mkstemp(prefix=".env.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
            archivo.write("\n".join(result) + "\n")
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, target)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise
    return target
