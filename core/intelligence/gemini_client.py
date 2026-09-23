"""
Frontera con el SDK de Gemini
=============================

Toda llamada a Gemini pasa por aquí: el motor de arquitectura, la prueba de
clave y el traductor. Es el único sitio que toca el SDK, y lo hace dentro de
`frontera`, que convierte cualquier excepción en `GeminiError` con el mensaje
ya saneado (AUD-031).

Sanear no es opcional porque el SDK repite la clave en el detalle de algunos
errores (la URL de la petición, con `?key=...`). Por eso:

- se quita la clave usada y cualquier otro valor con forma de clave de Google;
- la excepción original no viaja encadenada (`from None`): una traza en el
  log no puede arrastrar su mensaje.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

#: Forma de una clave de API de Google: «AIza» y 35 caracteres más.
KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z_\-]{35}")

#: Tope del mensaje que se deja pasar: basta para diagnosticar.
MAX_MESSAGE = 400

ClientFactory = Callable[[str], Any]


class GeminiError(RuntimeError):
    """Fallo de Gemini. Su mensaje ya está saneado."""


def sanitize(texto: str, api_key: str) -> str:
    """Quita la clave, y todo lo que tenga su forma, de un texto."""
    limpio = texto.replace(api_key, "***") if api_key else texto
    return KEY_PATTERN.sub("***", limpio)[:MAX_MESSAGE]


def _cliente_real(api_key: str) -> Any:
    from google import genai

    return genai.Client(api_key=api_key)


@contextmanager
def frontera(api_key: str) -> Iterator[None]:
    """Traduce cualquier fallo del SDK a `GeminiError` saneado."""
    try:
        yield
    except GeminiError:
        raise
    # Frontera con el SDK: lanza de muchas formas (red, cuota, argumentos) y
    # todas deben salir saneadas y sin la excepción original encadenada.
    except Exception as exc:  # noqa: BLE001
        raise GeminiError(sanitize(f"{type(exc).__name__}: {exc}", api_key)) from None


def stream_text(
    api_key: str,
    *,
    model: str,
    contents: str,
    config: Any,
    client_factory: ClientFactory | None = None,
) -> Iterator[str]:
    """Texto de `generate_content_stream`, trozo a trozo."""
    fabrica = client_factory or _cliente_real
    with frontera(api_key):
        cliente = fabrica(api_key)
        respuesta = cliente.models.generate_content_stream(
            model=model, contents=contents, config=config
        )
        for trozo in respuesta:
            texto = getattr(trozo, "text", None)
            if texto:
                yield texto


def generate_text(
    api_key: str,
    *,
    model: str,
    contents: str,
    config: Any,
    client_factory: ClientFactory | None = None,
) -> str:
    """Texto completo de `generate_content`."""
    fabrica = client_factory or _cliente_real
    with frontera(api_key):
        cliente = fabrica(api_key)
        respuesta = cliente.models.generate_content(
            model=model, contents=contents, config=config
        )
        return str(getattr(respuesta, "text", "") or "")
