"""
Acceso de SENTRA en el lanzador de Linux
========================================

En Windows el acceso era `Desktop\\SENTRA.lnk` → `sentra.exe`. En Linux es una
entrada de escritorio. Este script rellena `scripts/linux/sentra.desktop.in`
con la raíz real del repo y la instala en un solo sitio:
`$XDG_DATA_HOME/applications/sentra.desktop` (por defecto
`~/.local/share/applications/sentra.desktop`). Cualquier otra ruta se rechaza.

`StartupWMClass=sentra`: Tauri no da id de aplicación a GTK
(`enableGtkAppId` no está activo), así que GTK usa el nombre del programa,
`sentra` (el binario), como app_id en Wayland y como WM_CLASS en X11.

Uso
---
    python -m scripts.acceso_linux --en-seco   # enseña la entrada y el destino, no escribe
    python -m scripts.acceso_linux             # la instala (necesita la release compilada)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PLANTILLA = RAIZ / "scripts" / "linux" / "sentra.desktop.in"
MARCA = "@RAIZ@"
NOMBRE = "sentra.desktop"
#: Caracteres que no necesitan comillas ni escapes en Exec, Path e Icon.
_RUTA_SEGURA = re.compile(r"/[A-Za-z0-9._+/-]*")


def binario_release(raiz: Path = RAIZ) -> Path:
    return raiz / "ui" / "src-tauri" / "target" / "release" / "sentra"


def destino_permitido(entorno: Mapping[str, str]) -> Path:
    """`$XDG_DATA_HOME/applications/sentra.desktop`; una XDG_DATA_HOME relativa no vale."""
    datos = entorno.get("XDG_DATA_HOME", "")
    if not datos or not Path(datos).is_absolute():
        datos = str(Path(entorno["HOME"]) / ".local" / "share")
    return Path(datos) / "applications" / NOMBRE


def renderizar(raiz: Path = RAIZ) -> str:
    texto = str(raiz)
    if not _RUTA_SEGURA.fullmatch(texto):
        raise ValueError(
            f"La raíz {texto!r} tiene caracteres que habría que escapar en la entrada "
            "de escritorio (espacios, %, saltos de línea...). Mueve el repo a una ruta simple."
        )
    contenido = PLANTILLA.read_text(encoding="utf-8").replace(MARCA, texto)
    if "@" in contenido:
        raise ValueError("La plantilla tiene marcas sin rellenar.")
    return contenido


def _escribir(destino: Path, contenido: str) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(
        prefix=".sentra.", suffix=".tmp", dir=destino.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as archivo:
            archivo.write(contenido)
        os.chmod(temporal, 0o644)
        os.replace(temporal, destino)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise


def main(
    argv: Sequence[str] | None = None, entorno: Mapping[str, str] | None = None
) -> int:
    parser = argparse.ArgumentParser(
        description="Acceso de SENTRA en el lanzador de Linux"
    )
    parser.add_argument(
        "--en-seco",
        action="store_true",
        help="enseña la entrada y el destino sin escribir",
    )
    parser.add_argument(
        "--destino",
        type=Path,
        help="solo se acepta el destino permitido (para comprobarlo)",
    )
    parser.add_argument(
        "--binario", type=Path, default=binario_release(), help=argparse.SUPPRESS
    )
    args = parser.parse_args(argv)
    entorno = os.environ if entorno is None else entorno

    permitido = destino_permitido(entorno)
    destino: Path = args.destino if args.destino is not None else permitido
    if destino.absolute() != permitido.absolute():
        print(
            f"Me niego a escribir en {destino}: el único destino permitido es {permitido}.",
            file=sys.stderr,
        )
        return 2

    try:
        contenido = renderizar()
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2

    falta_binario = not args.binario.is_file()
    if args.en_seco:
        print(f"Destino: {permitido}")
        print(contenido, end="")
        if falta_binario:
            print(
                f"Aviso: todavía no existe la release en {args.binario}. "
                "Compílala antes de instalar el acceso.",
                file=sys.stderr,
            )
        return 0

    if falta_binario:
        print(
            f"No instalo el acceso: falta la release en {args.binario}. "
            "Compílala primero (cd ui && npm run tauri build).",
            file=sys.stderr,
        )
        return 1

    _escribir(permitido, contenido)
    print(f"Acceso instalado en {permitido}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
