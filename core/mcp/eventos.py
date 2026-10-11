"""
Registro común del escritorio 9 (adaptador)
===========================================

Cada `tools/call` del servidor MCP deja una línea en el registro común de
Claude (`~/.local/state/claude-escritorio/eventos.jsonl`): acción, argumentos y
resultado resumidos (la librería quita los secretos), duración y si escribió.
La librería es `~/Puente/comun/claude_eventos.py`, que el venv ve por un
`claude_eventos.pth`. Si no está, `registrar` devuelve el manejador tal cual y
el servidor sigue igual.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from typing import Any

try:
    _ce: Any = importlib.import_module("claude_eventos")
except ImportError:
    _ce = None

HERRAMIENTA = "sentra"
#: Lo único que cambia algo: deja una propuesta pendiente en la base (no gasta).
ESCRIBEN = frozenset({"proponer_escaneo"})

Manejar = Callable[[dict[str, Any]], "dict[str, Any] | None"]


def registrar(manejar: Manejar) -> Manejar:
    """`manejar` envuelto para que anote cada `tools/call`; sin la librería, el mismo `manejar`."""
    if _ce is None:
        return manejar
    # Bajo pytest, solo con un registro de prueba: una suite nunca escribe en el real.
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("CLAUDE_ESCRITORIO_DIR"):
        return manejar
    try:
        envuelto: Manejar = _ce.envolver_jsonrpc(
            HERRAMIENTA, manejar, escribe=lambda nombre, _args: nombre in ESCRIBEN
        )
    except Exception:  # noqa: BLE001 — el registro nunca tumba el servidor
        return manejar
    return envuelto
