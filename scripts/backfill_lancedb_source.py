"""
Relleno de la fuente en LanceDB (AUD-016, decisión D-J)
=======================================================

Las filas de LanceDB escritas antes de D-J no saben si vienen de la
demostración o de Reddit: al abrir la tabla ganan la columna `data_source`
vacía. Este script la rellena cruzando con PostgreSQL: cada fila hereda la
fuente de la señal con el mismo id (`analyzed_signals.reddit_id`), que a su
vez la heredó de su ejecución en la migración 007.

Si no hay señal con ese id, si su ejecución no registró fuente o si varias
ejecuciones discrepan, la fila se queda en NULL: la interfaz la muestra como
«desconocida». Solo se tocan filas vacías; una fuente ya escrita no se
sobrescribe.

Uso (después de aplicar la migración 007):

    python -m scripts.backfill_lancedb_source
    python -m scripts.backfill_lancedb_source --dsn "host=... dbname=..." --lance ruta
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Mapping, Sequence

from core.storage.lancedb_store import LanceDBStore, _sql_literal

FUENTES_VALIDAS = frozenset({"demo", "reddit"})


def fuentes_por_id(pares: Iterable[tuple[str, str | None]]) -> dict[str, str | None]:
    """Una fuente por id, o None si no se puede saber sin suponer.

    Las ejecuciones sin fuente no cuentan (no dicen nada); si las que sí la
    tienen discrepan, no se elige ninguna.
    """
    vistas: dict[str, set[str]] = {}
    for ident, fuente in pares:
        conocidas = vistas.setdefault(ident, set())
        if fuente in FUENTES_VALIDAS:
            conocidas.add(fuente)
    return {
        ident: next(iter(conocidas)) if len(conocidas) == 1 else None
        for ident, conocidas in vistas.items()
    }


def leer_fuentes(dsn: str) -> dict[str, str | None]:
    """Fuente de cada señal de PostgreSQL, por su id de Reddit.

    La de la propia señal y, si no la tiene, la de su ejecución.
    """
    import psycopg

    with psycopg.connect(dsn) as conn:
        filas = conn.execute(
            """
            SELECT s.reddit_id, COALESCE(s.data_source, r.data_source)
            FROM radar.analyzed_signals s
            LEFT JOIN radar.pipeline_runs r ON r.id = s.run_id
            """
        ).fetchall()
    return fuentes_por_id((str(ident), fuente) for ident, fuente in filas)


def rellenar_fuentes(store: LanceDBStore, fuentes: Mapping[str, str | None]) -> int:
    """Escribe la fuente en las filas vacías. Devuelve cuántos ids se rellenaron."""
    tabla = store._table
    vacias = {
        str(fila["id"])
        for fila in tabla.search().where("data_source IS NULL").select(["id"]).to_list()
    }
    rellenadas = 0
    for ident in sorted(vacias):
        fuente = fuentes.get(ident)
        if fuente not in FUENTES_VALIDAS:
            continue
        tabla.update(
            where=f"id = {_sql_literal(ident)} AND data_source IS NULL",
            values={"data_source": fuente},
        )
        rellenadas += 1
    return rellenadas


def main(argv: Sequence[str] | None = None) -> int:
    from scripts.migrate import _default_dsn

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dsn", default=None, help="DSN de PostgreSQL (por defecto, el del proyecto)")
    parser.add_argument("--lance", default=None, help="Ruta del almacén LanceDB")
    args = parser.parse_args(argv)

    store = LanceDBStore(db_path=args.lance)
    fuentes = leer_fuentes(args.dsn or _default_dsn())
    rellenadas = rellenar_fuentes(store, fuentes)
    desconocidas = sum(1 for f in fuentes.values() if f is None)
    print(f"Filas rellenadas: {rellenadas}. Ids sin fuente determinable: {desconocidas}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
