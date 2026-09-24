"""
Ruta de LanceDB y literales SQL seguros
=======================================

Lo que queda del almacén de la pipeline antigua: dónde vive LanceDB
(argumento > RIR_LANCEDB_PATH > raíz de datos) y el escape de literales
para sus predicados. Los vectores de la evidencia los guarda
`core.evidence.vectors.EvidenceVectorStore`. El almacén de «oportunidades»
(`LanceDBStore` y su tabla de LanceDB) y su relleno desde las tablas
antiguas se retiraron con ellas (AUD2-016).
"""

from __future__ import annotations

import os
from pathlib import Path

from .embeddings import HashEmbedder

# Variable de entorno que permite reubicar el almacen sin tocar codigo.
DB_PATH_ENV_VAR = "RIR_LANCEDB_PATH"


def resolve_db_path(db_path: str | Path | None = None) -> Path:
    """
    Resuelve la ruta del almacen LanceDB en cascada:

    1. El argumento explicito, si se proporciona.
    2. La variable de entorno ``RIR_LANCEDB_PATH``.
    3. ``<raiz de datos>/data/lancedb`` (``core.rutas.raiz_datos``).

    Nunca devuelve una ruta absoluta cableada a una unidad concreta: el
    proyecto debe poder moverse de disco o de maquina sin editar fuentes.
    """
    if db_path:
        return Path(db_path)

    from_env = os.environ.get(DB_PATH_ENV_VAR)
    if from_env:
        return Path(from_env)

    from core.rutas import raiz_datos

    return raiz_datos() / "data" / "lancedb"


def _sql_literal(value: str) -> str:
    """
    Convierte una cadena en un literal SQL seguro, duplicando las comillas
    simples segun el estandar SQL.

    LanceDB acepta predicados como cadena y no expone enlace de parametros,
    asi que el escape en origen es la unica defensa frente a la inyeccion.

        _sql_literal("o'brien")  ->  "'o''brien'"
    """
    if not isinstance(value, str):
        raise TypeError(
            f"Un literal SQL debe construirse desde str, no desde {type(value).__name__}"
        )
    return "'" + value.replace("'", "''") + "'"


# Alias historico. El generador por hash vive en embeddings.py y ha dejado de
# ser el proveedor por defecto: no es semantico.
DefaultTextEmbedder = HashEmbedder
