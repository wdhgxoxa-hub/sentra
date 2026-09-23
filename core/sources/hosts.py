"""Dominios que vienen de la configuración del usuario (instancias, foros).

Antes de construir una URL con un valor de la tarjeta o del perfil, se
exige que sea un dominio y nada más: ni ruta, ni usuario, ni puerto.
"""

from __future__ import annotations

import re

_DOMINIO = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def domain(valor: str, *, require_https: bool = False) -> str | None:
    """El dominio en minúsculas, o None si el valor no es solo un dominio.

    Admite `dominio`, `https://dominio` y `https://dominio/`; con
    `require_https`, el esquema https:// es obligatorio.
    """
    limpio = valor.strip().lower()
    if require_https and not limpio.startswith("https://"):
        return None
    limpio = limpio.removeprefix("https://").removeprefix("http://").rstrip("/")
    return limpio if _DOMINIO.match(limpio) else None
