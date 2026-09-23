"""
Proveedor Gemini: la frontera con el SDK
========================================

Toda llamada a Gemini pasa por aquí: el motor de arquitectura, la prueba de
clave y el traductor. Es el único módulo del proyecto que importa el SDK
(`tests/test_llm_boundary.py` lo comprueba).

Saneado (AUD-031)
-----------------
`frontera` convierte cualquier excepción en `GeminiError` con el mensaje ya
saneado: el SDK repite la clave en el detalle de algunos errores (la URL de
la petición, con `?key=...`). Se quita la clave usada y cualquier otro valor
con forma de clave de Google, y la excepción original no viaja encadenada
(`from None`): una traza en el log no puede arrastrar su mensaje.

Robustez (AUD-020)
------------------
- Cada petición lleva timeout y límite de salida explícitos.
- Los errores transitorios (sobrecarga, cuota, red, timeout) se reintentan
  con espera creciente; los permanentes (clave mala, petición inválida), no.
  En streaming solo se reintenta ANTES del primer trozo: después, repetir
  pintaría el principio del documento dos veces.
- Una respuesta bloqueada, vacía o cortada por longitud es un error tipado,
  nunca un texto vacío que alguien dé por bueno.

Cada error tiene un `code` estable que la interfaz traduce.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import httpx

from .base import LLMError

#: Forma de una clave de API de Google: «AIza» y 35 caracteres más.
KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z_\-]{35}")

#: Tope del mensaje que se deja pasar: basta para diagnosticar.
MAX_MESSAGE = 400

#: Reintentos tras el primer intento ante un error transitorio.
MAX_RETRIES = 3

#: Espera antes del reintento n (0, 1, 2...): BACKOFF_BASE_S * 2**n segundos.
BACKOFF_BASE_S = 2.0

#: Motivos de fin que significan que el modelo se negó a seguir.
BLOCKING_FINISH_REASONS = frozenset({
    "SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII",
    "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT",
})

#: Motivo de fin cuando se agota `max_output_tokens`.
TRUNCATING_FINISH_REASON = "MAX_TOKENS"

ClientFactory = Callable[[str], Any]

#: La espera entre reintentos; los tests la sustituyen para no dormir.
_esperar = time.sleep


class GeminiError(LLMError):
    """Fallo de Gemini (ver `LLMError`). Los códigos `gemini_*` son los que
    la interfaz ya traduce."""

    code = "gemini_error"


class GeminiUnavailable(GeminiError):
    """El servicio está caído o sobrecargado (5xx, fallo de red)."""

    code = "gemini_unavailable"
    transient = True


class GeminiRateLimited(GeminiError):
    """Cuota o ritmo de peticiones agotado (429)."""

    code = "gemini_rate_limited"
    transient = True


class GeminiTimeout(GeminiError):
    """La petición superó su timeout."""

    code = "gemini_timeout"
    transient = True


class GeminiBlocked(GeminiError):
    """El modelo bloqueó la petición o cortó la respuesta por seguridad."""

    code = "gemini_blocked"


class GeminiEmpty(GeminiError):
    """El modelo terminó sin devolver texto."""

    code = "gemini_empty"


class GeminiTruncated(GeminiError):
    """La respuesta se cortó al agotar `max_output_tokens`."""

    code = "gemini_truncated"


class GeminiIncomplete(GeminiError):
    """Al documento le faltan secciones exigidas; `missing` dice cuáles."""

    code = "gemini_incomplete"


#: Estados HTTP transitorios y el error que les corresponde.
_POR_ESTADO: dict[int, type[GeminiError]] = {
    408: GeminiTimeout,
    429: GeminiRateLimited,
    500: GeminiUnavailable,
    502: GeminiUnavailable,
    503: GeminiUnavailable,
    504: GeminiUnavailable,
}


def sanitize(texto: str, api_key: str) -> str:
    """Quita la clave, y todo lo que tenga su forma, de un texto."""
    limpio = texto.replace(api_key, "***") if api_key else texto
    return KEY_PATTERN.sub("***", limpio)[:MAX_MESSAGE]


def _clase_de(exc: BaseException) -> type[GeminiError]:
    if isinstance(exc, httpx.TimeoutException):
        return GeminiTimeout
    if isinstance(exc, httpx.TransportError):
        return GeminiUnavailable
    estado = getattr(exc, "code", None)
    if isinstance(estado, int):
        return _POR_ESTADO.get(estado, GeminiError)
    return GeminiError


def _cliente_real(api_key: str) -> Any:
    from google import genai

    return genai.Client(api_key=api_key)


def build_config(
    *,
    timeout_ms: int,
    max_output_tokens: int,
    system_instruction: str | None = None,
    temperature: float | None = None,
) -> Any:
    """Configuración de una petición, siempre con timeout y límite de salida."""
    from google.genai import types

    return types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        http_options=types.HttpOptions(timeout=timeout_ms),
    )


@contextmanager
def frontera(api_key: str) -> Iterator[None]:
    """Traduce cualquier fallo del SDK a un `GeminiError` tipado y saneado."""
    try:
        yield
    except GeminiError:
        raise
    # Frontera con el SDK: lanza de muchas formas (red, cuota, argumentos) y
    # todas deben salir tipadas, saneadas y sin la excepción original.
    except Exception as exc:  # noqa: BLE001 - frontera con el SDK de Gemini
        clase = _clase_de(exc)
        raise clase(sanitize(f"{type(exc).__name__}: {exc}", api_key)) from None


def _revisar(respuesta: Any) -> None:
    """Lanza si el trozo (o la respuesta) dice que el modelo se negó o cortó."""
    feedback = getattr(respuesta, "prompt_feedback", None)
    bloqueo = getattr(feedback, "block_reason", None)
    if bloqueo is not None:
        nombre = getattr(bloqueo, "name", str(bloqueo))
        raise GeminiBlocked(f"Petición bloqueada por el modelo: {nombre}")

    for candidato in getattr(respuesta, "candidates", None) or []:
        fin = getattr(candidato, "finish_reason", None)
        if fin is None:
            continue
        nombre = getattr(fin, "name", str(fin))
        if nombre in BLOCKING_FINISH_REASONS:
            raise GeminiBlocked(f"Respuesta cortada por el modelo: {nombre}")
        if nombre == TRUNCATING_FINISH_REASON:
            raise GeminiTruncated(
                "La respuesta se cortó al agotar el límite de salida del modelo."
            )


def _texto(respuesta: Any) -> str:
    """El texto de un trozo, o cadena vacía (un trozo sin partes no lo tiene)."""
    try:
        return str(getattr(respuesta, "text", None) or "")
    # El SDK puede lanzar si el trozo solo trae metadatos; no es un fallo.
    except (ValueError, AttributeError):
        return ""


def _reintentar(intento: int, exc: GeminiError, max_retries: int) -> None:
    """Espera antes del siguiente intento, o relanza si no toca reintentar."""
    if not exc.transient or intento >= max_retries:
        raise exc
    _esperar(BACKOFF_BASE_S * 2 ** intento)


def stream_text(
    api_key: str,
    *,
    model: str,
    contents: str,
    config: Any,
    client_factory: ClientFactory | None = None,
    max_retries: int = MAX_RETRIES,
) -> Iterator[str]:
    """Texto de `generate_content_stream`, trozo a trozo.

    Termina con error tipado si el modelo bloquea, corta o no dice nada.
    """
    fabrica = client_factory or _cliente_real
    for intento in range(max_retries + 1):
        entregado = False
        try:
            with frontera(api_key):
                # El cliente se guarda en una variable a propósito: al destruirse
                # cierra su transporte HTTP, y como temporal CPython lo destruía
                # antes de enviar nada. Tiene que vivir hasta agotar el stream.
                cliente = fabrica(api_key)
                respuesta = cliente.models.generate_content_stream(
                    model=model, contents=contents, config=config
                )
                for trozo in respuesta:
                    texto = _texto(trozo)
                    if texto:
                        entregado = True
                        yield texto
                    _revisar(trozo)
        except GeminiError as exc:
            if entregado:
                raise
            _reintentar(intento, exc, max_retries)
            continue
        if not entregado:
            raise GeminiEmpty("El modelo terminó sin devolver texto.")
        return


def generate_text(
    api_key: str,
    *,
    model: str,
    contents: str,
    config: Any = None,
    client_factory: ClientFactory | None = None,
    max_retries: int = MAX_RETRIES,
) -> str:
    """Texto completo de `generate_content`, con las mismas garantías."""
    fabrica = client_factory or _cliente_real
    for intento in range(max_retries + 1):
        try:
            with frontera(api_key):
                cliente = fabrica(api_key)  # vivo durante la petición (ver stream_text)
                respuesta = cliente.models.generate_content(
                    model=model, contents=contents, config=config
                )
                _revisar(respuesta)
                texto = _texto(respuesta)
        except GeminiError as exc:
            _reintentar(intento, exc, max_retries)
            continue
        if not texto:
            raise GeminiEmpty("El modelo terminó sin devolver texto.")
        return texto
    raise AssertionError("inalcanzable: el último intento devuelve o relanza")


def ping(
    api_key: str,
    *,
    model: str,
    config: Any,
    client_factory: ClientFactory | None = None,
) -> None:
    """Comprueba que clave y modelo responden: basta con el primer trozo.

    Sin reintentos ni exigencia de texto: un modelo de razonamiento puede
    gastar el primer trozo pensando, y eso ya demuestra que la clave sirve.
    """
    fabrica = client_factory or _cliente_real
    with frontera(api_key):
        cliente = fabrica(api_key)  # vivo durante la petición (ver stream_text)
        respuesta = cliente.models.generate_content_stream(
            model=model, contents="ping", config=config
        )
        for trozo in respuesta:
            try:
                _revisar(trozo)
            except GeminiTruncated:
                pass  # agotar el límite de la prueba no dice nada de la clave
            break
