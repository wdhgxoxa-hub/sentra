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


class AuthorSaltMissing(RuntimeError):
    """Hay un autor que guardar y no hay sal: no se guarda en claro ni con una sal inventada.

    Una sal inventada por proceso cambiaría en cada ejecución y rompería, sin
    avisar, el recuento de autores distintos (G2).
    """

#: Marcas de autor borrado: no son una persona y no cuentan como autor.
_SIN_AUTOR = frozenset({"", "[deleted]", "[removed]", "deleted", "ghost"})


def _normalizado(username: str | None) -> str:
    # lower() y no casefold(): la migración 009 calcula el mismo hash en SQL
    # con lower(), y los dos tienen que coincidir.
    return (username or "").strip().lower()


def es_autor_identificable(username: str | None) -> bool:
    """False para vacíos y marcas de borrado: no son una persona."""
    return _normalizado(username) not in _SIN_AUTOR


def author_hash(source: str, username: str | None, salt: str) -> str | None:
    """Hash del autor en su fuente; None si no hay autor identificable."""
    if not es_autor_identificable(username):
        return None
    mensaje = f"{source}:{_normalizado(username)}".encode()
    return hmac.new(salt.encode(), mensaje, hashlib.sha256).hexdigest()


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
