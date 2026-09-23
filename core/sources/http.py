"""Cliente HTTP de las fuentes: un solo punto de creación (los tests lo sustituyen).

Algunas APIs llevan la credencial en la URL (Stack Exchange: `key=`) y httpx
registra cada URL a nivel INFO. `RedactSecrets` tapa esos parámetros en el
logger de httpx antes de escribir nada (R6).
"""

from __future__ import annotations

import logging
import re

import httpx

#: Parámetros de consulta cuyo valor nunca se escribe en un log.
_SECRETOS = re.compile(
    r"(?i)([?&](?:key|access_token|token|client_secret|api_key|apikey)=)[^&\s\"']*")


class RedactSecrets(logging.Filter):
    """Sustituye el valor de los parámetros secretos por ***."""

    def filter(self, record: logging.LogRecord) -> bool:
        mensaje = record.getMessage()
        limpio = _SECRETOS.sub(r"\1***", mensaje)
        if limpio != mensaje:
            record.msg, record.args = limpio, ()
        return True


def _instalar() -> None:
    registro = logging.getLogger("httpx")
    if not any(isinstance(f, RedactSecrets) for f in registro.filters):
        registro.addFilter(RedactSecrets())


_instalar()


def new_client() -> httpx.AsyncClient:
    """Cliente para hablar con las APIs de las fuentes."""
    return httpx.AsyncClient(follow_redirects=False)
