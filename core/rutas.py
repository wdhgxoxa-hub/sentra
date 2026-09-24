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

import os
from pathlib import Path

DATA_DIR_ENV_VAR = "RIR_DATA_DIR"

#: <raíz>/core/rutas.py → la raíz del código del motor (repo o copia versionada).
RAIZ_CODIGO = Path(__file__).resolve().parents[1]


def raiz_datos() -> Path:
    """Carpeta del proyecto con el `.env` y `data/`."""
    valor = os.environ.get(DATA_DIR_ENV_VAR, "").strip()
    return Path(valor) if valor else RAIZ_CODIGO
