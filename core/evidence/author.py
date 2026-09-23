"""
Autores anónimos (R9)
=====================

El nombre de usuario no se guarda nunca. Se guarda un HMAC-SHA256 con una
sal local (32 bytes aleatorios, generada una vez por instalación y guardada
en el .env con escritura atómica), que sirve para una sola cosa: contar
autores distintos (compuerta G2) sin saber quién es nadie.

El hash lleva la fuente delante: «ana» en Reddit y «ana» en GitHub cuentan
como dos autores, porque no hay forma de saber si son la misma persona, y
fundirlos inflaría o desinflaría G2 sin evidencia.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from core.envfile import default_env_path, update_dotenv

AUTHOR_SALT_ENV = "RIR_AUTHOR_SALT"

#: Marcas de autor borrado: no son una persona y no cuentan como autor.
_SIN_AUTOR = frozenset({"", "[deleted]", "[removed]", "deleted", "ghost"})


def author_hash(source: str, username: str | None, salt: str) -> str | None:
    """Hash del autor en su fuente; None si no hay autor identificable."""
    nombre = (username or "").strip().casefold()
    if nombre in _SIN_AUTOR:
        return None
    return hmac.new(salt.encode(), f"{source}:{nombre}".encode(), hashlib.sha256).hexdigest()


def load_or_create_salt(env_path: str | None = None) -> str:
    """La sal de esta instalación; la crea y la guarda la primera vez."""
    from core.ingestion.auth import load_dotenv

    ruta = env_path or default_env_path()
    guardada = (load_dotenv(ruta, env={}).get(AUTHOR_SALT_ENV) or "").strip()
    if guardada:
        return guardada
    nueva = secrets.token_hex(32)
    update_dotenv({AUTHOR_SALT_ENV: nueva}, ruta)
    return nueva
