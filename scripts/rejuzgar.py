"""
Re-juicio de un escaneo guardado (AUD2-001, 6.4)
===============================================

    python scripts/rejuzgar.py --run <id del escaneo> [--dsn DSN]

Pasa el juez actual por la evidencia que ya guardó un escaneo, sin escanear
de nuevo, y lo guarda como una ejecución nueva «rejuicio» (el escaneo de
origen no se toca). Usa el mismo proveedor que el escaneo (el modelo general
guardado en Ajustes), la caché de etiquetas de PostgreSQL y los vectores e5
guardados. Gasta llamadas reales a Gemini: dice cuántas y con cuántos tokens.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.judge.rejuicio import rejuzgar


def _proveedor(dsn: str) -> tuple[Any, str | None, str | None]:
    """(proveedor, modelo, motivo): exactamente la resolución del escaneo."""
    from core.orchestration.sidecar.context import SidecarContext
    from core.orchestration.sidecar.multiscan import _proveedor_del_juez

    ctx = SidecarContext(persist_default=True, postgres_dsn=dsn, env_path=None, started_at=time.monotonic())
    return _proveedor_del_juez(ctx)


def _vectores() -> Callable[[Sequence[str]], Mapping[str, Sequence[float]]]:
    from core.evidence.vectors import EvidenceVectorStore

    almacen = EvidenceVectorStore()
    return almacen.vectors


def main(argv: list[str] | None = None) -> int:
    from core.storage.postgres_store import resolver_dsn

    parser = argparse.ArgumentParser(description="Re-juzga un escaneo guardado con el juez actual")
    parser.add_argument("--run", required=True, help="id del escaneo de origen (pipeline_runs.id)")
    parser.add_argument("--dsn", default=None)
    args = parser.parse_args(argv)
    dsn = resolver_dsn(args.dsn)

    proveedor, modelo, motivo = _proveedor(dsn)
    if proveedor is None:
        print(f"No se re-juzga: sin proveedor del juez ({motivo}). Sin etiquetas no hay nichos.")
        return 2

    from core.judge.store import PostgresLabelCache

    nueva, resumen = rejuzgar(dsn, args.run, provider=proveedor, model=modelo,
                              cache=PostgresLabelCache(dsn), vectores=_vectores(), now=datetime.now(UTC))
    uso = list(getattr(proveedor, "usage", []) or [])
    print(f"ejecución nueva: {nueva} (rejuicio de {args.run})")
    print(f"modelo: {modelo} · llamadas al LLM: {len(uso)}")
    for n, u in enumerate(uso, 1):
        print(f"  {n}. {u.model}: {u.input_tokens} → {u.output_tokens} (+{u.reasoning_tokens} razonamiento)"
              f" en {u.duration_s:.1f} s")
    print(f"resumen: {resumen}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
