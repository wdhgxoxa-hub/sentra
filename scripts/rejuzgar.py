"""
Re-juicio de un escaneo guardado (AUD2-001, 6.4)
===============================================

    python scripts/rejuzgar.py --run <id del escaneo> [--dsn DSN] [--max-llamadas N] [--max-etiquetas N]

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
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.judge.rejuicio import rejuzgar

if TYPE_CHECKING:
    from core.evidence.vectors import EvidenceVectorStore


def _proveedor(dsn: str) -> tuple[Any, str | None, str | None]:
    """(proveedor, modelo, motivo): exactamente la resolución del escaneo."""
    from core.orchestration.sidecar.context import SidecarContext
    from core.orchestration.sidecar.multiscan import _proveedor_del_juez
    from core.rutas import ruta_cache_modelos_gemini

    # La lista de modelos guardada (AUD2-019): el re-juicio no la vuelve a pedir a Google.
    ctx = SidecarContext(persist_default=True, postgres_dsn=dsn, env_path=None, started_at=time.monotonic(),
                         cache_modelos=ruta_cache_modelos_gemini())
    return _proveedor_del_juez(ctx)


class ProveedorConTope:
    """R7: deja pasar como mucho `maximo` llamadas; la siguiente es
    LLMBudgetExhausted y no sale. El juez hace entonces lo seguro: etiqueta
    undetermined, G0 sin comprobar y CONSTRUIR sin revisar baja."""

    def __init__(self, proveedor: Any, maximo: int) -> None:
        self.proveedor, self.maximo, self.hechas = proveedor, maximo, 0

    @property
    def usage(self) -> Any:
        return getattr(self.proveedor, "usage", [])

    def generate_json(self, *args: Any, **kwargs: Any) -> Any:
        from core.llm.base import LLMBudgetExhausted

        if self.hechas >= self.maximo:
            raise LLMBudgetExhausted(f"tope de {self.maximo} llamadas del re-juicio (R7)")
        self.hechas += 1
        return self.proveedor.generate_json(*args, **kwargs)


def _almacen() -> EvidenceVectorStore:
    from core.evidence.vectors import EvidenceVectorStore

    return EvidenceVectorStore()


def main(argv: list[str] | None = None) -> int:
    from core.storage.postgres_store import resolver_dsn

    # Redirigida a un archivo, la salida de Windows es cp1252 y el informe usa «→».
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Re-juzga un escaneo guardado con el juez actual")
    parser.add_argument("--run", required=True, help="id del escaneo de origen (pipeline_runs.id)")
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--max-llamadas", type=int, default=None,
                        help="tope de llamadas al LLM (R7); al llegar, el juez hace lo seguro")
    parser.add_argument("--max-etiquetas", type=int, default=None,
                        help="tope de piezas etiquetadas (por defecto, el del escaneo)")
    args = parser.parse_args(argv)
    dsn = resolver_dsn(args.dsn)

    proveedor, modelo, motivo = _proveedor(dsn)
    if proveedor is None:
        print(f"No se re-juzga: sin proveedor del juez ({motivo}). Sin etiquetas no hay nichos.")
        return 2

    from core.judge.labels import MAX_ITEMS_PER_SCAN
    from core.judge.store import PostgresLabelCache

    if args.max_llamadas is not None:
        proveedor = ProveedorConTope(proveedor, args.max_llamadas)

    almacen = _almacen()
    nueva, resumen = rejuzgar(dsn, args.run, provider=proveedor, model=modelo,
                              cache=PostgresLabelCache(dsn), vectores=almacen.vectors,
                              vectores_frase=almacen.embed_frases, now=datetime.now(UTC),
                              label_max_items=MAX_ITEMS_PER_SCAN if args.max_etiquetas is None else args.max_etiquetas)
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
