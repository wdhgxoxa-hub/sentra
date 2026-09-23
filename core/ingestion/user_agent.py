"""
User-Agent de la API de Reddit (AUD-014)
========================================

Reddit exige que cada cliente se identifique, y lo trata como credencial:
un UA genérico o de navegador acaba limitado o bloqueado. El formato que
pide su documentación es

    <plataforma>:<app>:<versión> (by /u/<usuario>)

p. ej. `windows:sentra:0.1.0 (by /u/alguien)`. Es obligatorio: no hay valor
por defecto, porque cualquier valor por defecto sería uno de relleno.
"""

from __future__ import annotations

import re

from .errors import RedditUserAgentInvalid

#: `<plataforma>:<app>:<versión> (by /u/<usuario>)`. El usuario, con las
#: reglas de nombre de Reddit (3-20 caracteres: letras, cifras, _ y -).
USER_AGENT_PATTERN = re.compile(
    r"^(?P<plataforma>[A-Za-z0-9_.\-]+):(?P<app>[A-Za-z0-9_.\-]+):(?P<version>[A-Za-z0-9_.\-]+)"
    r" \(by /u/(?P<usuario>[A-Za-z0-9_\-]{3,20})\)$"
)

#: Usuarios de ejemplo que la interfaz o la documentación sugieren: un UA
#: con uno de ellos no identifica a nadie.
USUARIOS_DE_RELLENO = frozenset({"tu_usuario", "your_username", "unknown", "username"})

FORMATO = "<plataforma>:<app>:<versión> (by /u/<usuario>)"


def validar_user_agent(user_agent: str | None) -> str:
    """Devuelve el UA si identifica de verdad a la app y a su autor.

    Raises:
        RedditUserAgentInvalid: si falta, no sigue el formato o el usuario
            es de relleno.
    """
    valor = (user_agent or "").strip()
    encontrado = USER_AGENT_PATTERN.match(valor)
    if encontrado is None:
        raise RedditUserAgentInvalid(f"El User-Agent debe tener la forma {FORMATO}.")
    if encontrado.group("usuario").lower() in USUARIOS_DE_RELLENO:
        raise RedditUserAgentInvalid(
            f"El User-Agent usa un usuario de ejemplo ({encontrado.group('usuario')}): "
            "pon tu usuario de Reddit."
        )
    return valor
