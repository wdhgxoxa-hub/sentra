"""
Propuestas de escaneo (migración 021)
=====================================

Claude Desktop las deja por MCP (core/mcp); la ventana de SENTRA las enseña
y Walter las lanza o las descarta. Lanzar es un escaneo normal, con su
estimación confirmada: el motor marca la propuesta como lanzada solo después
de aceptar esa confirmación. Una propuesta se resuelve una sola vez.
"""

from __future__ import annotations

import re
from typing import Any

import psycopg

from core.storage.postgres_store import DEFAULT_TENANT_ID

_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_OPCIONES = "-c search_path=radar,public"


def pendientes(dsn: str, tenant_id: str = DEFAULT_TENANT_ID) -> list[dict[str, Any]]:
    """Las pendientes, de la más antigua a la más nueva."""
    with psycopg.connect(dsn, connect_timeout=5, options=_OPCIONES) as conn:
        conn.read_only = True
        filas = conn.execute(
            "SELECT id::text, profile, reason, created_at FROM scan_requests"
            " WHERE tenant_id = %s AND status = 'pendiente' ORDER BY created_at, id", (tenant_id,)).fetchall()
    return [{"id": f[0], "profile": f[1], "reason": f[2], "created_at": f[3].isoformat()} for f in filas]


def _resolver(dsn: str, tenant_id: str, id_: str, estado: str, run_id: str | None) -> bool:
    if not _UUID.fullmatch(id_) or (run_id is not None and not _UUID.fullmatch(run_id)):
        return False
    with psycopg.connect(dsn, connect_timeout=5, options=_OPCIONES) as conn:
        cursor = conn.execute(
            "UPDATE scan_requests SET status = %s, resolved_at = now(), run_id = %s"
            " WHERE tenant_id = %s AND id = %s AND status = 'pendiente'", (estado, run_id, tenant_id, id_))
        return cursor.rowcount == 1


def descartar(dsn: str, id_: str, tenant_id: str = DEFAULT_TENANT_ID) -> bool:
    """True si estaba pendiente y queda descartada."""
    return _resolver(dsn, tenant_id, id_, "descartada", None)


def marcar_lanzada(dsn: str, id_: str, run_id: str | None, tenant_id: str = DEFAULT_TENANT_ID) -> bool:
    """True si estaba pendiente y queda lanzada (con su ejecución si se guardó)."""
    return _resolver(dsn, tenant_id, id_, "lanzada", run_id)
