"""
El archivo .env del proyecto: escritura atómica
===============================================

Guarda las credenciales de todas las fuentes y la sal de los autores. Se
reescribe entero en un temporal de la misma carpeta y se sustituye con
`os.replace`, que es atómico: si el proceso muere a mitad, queda el archivo
anterior, nunca uno truncado sin claves. Se reescribe en lugar de anexar:
anexar dejaría duplicados y la última línea ganaría en silencio.

Lo que se escribe tiene que volver igual al leerlo (AUD-036): una clave es
un nombre de variable; un valor no lleva caracteres de control (un salto de
línea inyectaría otra variable), y si al leerlo perdería espacios o
comillas de los extremos, se escribe entre comillas dobles, que el lector
quita una sola vez.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

_CLAVE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CONTROL = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")


class EnvValueInvalid(ValueError):
    """Una clave o un valor que no se puede escribir en el `.env` tal cual."""

    code = "env_value_invalid"


def _linea(clave: str, valor: str) -> str:
    """`CLAVE=valor`, entre comillas si leerlo sin ellas lo alteraría."""
    if not _CLAVE.fullmatch(clave):
        raise EnvValueInvalid(f"«{clave}» no es un nombre de variable válido.")
    if _CONTROL.search(valor):
        raise EnvValueInvalid(f"El valor de {clave} lleva caracteres de control (saltos de línea).")
    extremos = len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'"
    if valor != valor.strip() or extremos:
        valor = f'"{valor}"'
    return f"{clave}={valor}"


def default_env_path() -> str:
    """Ruta del `.env` del proyecto (en la raíz de datos, no junto al código)."""
    from core.rutas import raiz_datos

    return str(raiz_datos() / ".env")


def update_dotenv(values: dict[str, str], path: str | None = None) -> Path:
    """Escribe o actualiza claves en un `.env`, preservando el resto.

    Lanza EnvValueInvalid, sin tocar el archivo, si alguna clave o valor no
    se puede escribir tal cual.
    """
    nuevas = {clave: _linea(clave, valor) for clave, valor in values.items()}
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
                pending.pop(key)
                result.append(nuevas[key])
                continue
        result.append(line)
    result.extend(nuevas[key] for key in pending)

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
