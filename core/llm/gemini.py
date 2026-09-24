"""
Proveedor Gemini: la frontera con el SDK
========================================

Toda llamada a Gemini pasa por aquí: el juez (etiquetado, coherencia y
abogado), los documentos y la prueba de clave. Es el único módulo del
proyecto que importa el SDK (`tests/test_llm_boundary.py` lo comprueba).

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
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ValidationError

from .base import (
    LLMError,
    LLMInvalidJson,
    LLMModelUnavailable,
    LLMTruncated,
    ModelInfo,
    UsageRecord,
)
from .budget import LLMBudget

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


class GeminiTruncated(GeminiError, LLMTruncated):
    """La respuesta se cortó al agotar `max_output_tokens`."""

    code = "gemini_truncated"


class GeminiIncomplete(GeminiError):
    """Al documento le faltan secciones exigidas; `missing` dice cuáles."""

    code = "gemini_incomplete"


class GeminiSinConfigurar(GeminiError):
    """No hay clave de API guardada."""

    code = "gemini_not_configured"


class GeminiKeyRejected(GeminiError):
    """Google rechaza la clave: no es válida (400 API_KEY_INVALID) o no tiene
    permiso (401/403). Es lo único que permite decir «la clave no funciona»;
    un fallo de red, de cuota o del servidor no dice nada de ella (D1)."""

    code = "gemini_key_rejected"


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
    if estado in (401, 403) or (estado == 400 and _clave_invalida(exc)):
        return GeminiKeyRejected
    if isinstance(estado, int):
        return _POR_ESTADO.get(estado, GeminiError)
    return GeminiError


def _clave_invalida(exc: BaseException) -> bool:
    """¿Un 400 que es la clave (razón API_KEY_INVALID) y no otra cosa?"""
    detalle = f"{getattr(exc, 'details', '')} {getattr(exc, 'message', '')}"
    return "API_KEY_INVALID" in detalle or "API key not valid" in detalle


def _cliente_real(api_key: str) -> Any:
    from google import genai

    return genai.Client(api_key=api_key)


def _build_config(
    *,
    timeout_ms: int,
    max_output_tokens: int,
    system_instruction: str | None = None,
    temperature: float | None = None,
    response_json_schema: dict[str, Any] | None = None,
    thinking_budget: int | None = None,
) -> Any:
    """Configuración de una petición, siempre con timeout y límite de salida.

    Con `response_json_schema`, la salida estructurada nativa de la API: el
    modelo responde JSON conforme a ese esquema.
    """
    from google.genai import types

    return types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        http_options=types.HttpOptions(timeout=timeout_ms),
        response_mime_type="application/json" if response_json_schema is not None else None,
        response_json_schema=response_json_schema,
        # En Gemini 3.x el razonamiento cuenta dentro de max_output_tokens.
        thinking_config=(types.ThinkingConfig(thinking_budget=thinking_budget)
                         if thinking_budget is not None else None),
    )


def _json_cortado(exc: ValidationError) -> bool:
    """¿El fallo es JSON que termina antes de tiempo (EOF), no un JSON inválido?"""
    return any(e.get("type") == "json_invalid" and "EOF" in str(e.get("msg", ""))
               for e in exc.errors())


#: Intentos de `generate_json`: el primero y UN reintento con el error.
JSON_ATTEMPTS = 2


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


# --- Modelos en vivo (F1.2, F1.3) ---------------------------------------------

#: Familia de modelos admitida. La 2.5 está en retirada: no se elige nunca por
#: defecto (el usuario puede guardar cualquiera de la lista si lo prefiere).
FAMILIA = 3

#: Nombre de un modelo de texto de Gemini: «gemini-3.6-flash»,
#: «gemini-3.1-pro-preview», «gemini-3-flash-preview-09-2026»...
_NOMBRE = re.compile(r"^gemini-(?P<mayor>\d+)(?:\.(?P<menor>\d+))?-(?P<tipo>flash|pro)(?P<resto>.*)$")

#: Sufijo de un modelo estable: ninguno, o una versión fijada («-001»).
_ESTABLE = re.compile(r"^(-\d{3})?$")

#: Sufijo de una vista previa del modelo base (con fecha o sin ella). Las
#: variantes (lite, image, tts, live, customtools...) no encajan en ninguno.
_PREVIA = re.compile(r"^-preview(-\d{2}-\d{4})?$")

UsoDeModelo = Literal["defecto", "documentos"]


def _candidato(modelo: ModelInfo, tipo: str, admite_previa: bool) -> tuple[int, int, int] | None:
    """Clave de orden si el modelo sirve para ese uso; None si no."""
    partes = _NOMBRE.match(modelo.id)
    if partes is None or partes["tipo"] != tipo or int(partes["mayor"]) != FAMILIA:
        return None
    resto = partes["resto"]
    if _ESTABLE.match(resto):
        estable = 1
    elif admite_previa and _PREVIA.match(resto):
        estable = 0
    else:
        return None
    return int(partes["menor"] or 0), estable, len(resto)


def elegir_modelo(
    modelos: Sequence[ModelInfo],
    uso: UsoDeModelo,
    guardado: str | None = None,
) -> ModelInfo:
    """El modelo que se usa, elegido entre los que la clave puede usar.

    - Si hay uno guardado y sigue en la lista, ese: la elección del usuario manda.
      Si ya no está, error tipado que pide elegir otro, nunca un cambio silencioso.
    - Por defecto: el Flash ESTABLE de la familia 3.x con la versión más alta.
    - Para documentos: el Pro más reciente de la familia 3.x, estable o en vista
      previa; a igual versión gana el estable.
    """
    if guardado:
        for modelo in modelos:
            if modelo.id == guardado:
                return modelo
        raise LLMModelUnavailable(
            f"El modelo guardado {guardado} ya no está disponible para esta clave; "
            "elige otro en Ajustes."
        )

    tipo, admite_previa = ("flash", False) if uso == "defecto" else ("pro", True)
    puntuados = [
        (clave, modelo)
        for modelo in modelos
        if (clave := _candidato(modelo, tipo, admite_previa)) is not None
    ]
    if not puntuados:
        estabilidad = "estable " if not admite_previa else ""
        raise LLMModelUnavailable(
            f"La clave no tiene ningún Gemini {FAMILIA}.x {tipo} {estabilidad}disponible; "
            "elige un modelo en Ajustes."
        )
    return max(puntuados, key=lambda par: par[0])[1]


def _uso(respuesta: Any) -> tuple[int | None, int | None, int | None]:
    """Tokens de entrada, salida y razonamiento que informa una respuesta."""
    meta = getattr(respuesta, "usage_metadata", None)
    if meta is None:
        return None, None, None
    return (
        getattr(meta, "prompt_token_count", None),
        getattr(meta, "candidates_token_count", None),
        getattr(meta, "thoughts_token_count", None),
    )


class GeminiProvider:
    """Implementación de `LLMProvider` sobre el SDK de Gemini.

    Conserva las garantías de AUD-020 (timeout y límite explícitos,
    reintentos solo transitorios y nunca tras entregar texto, bloqueo,
    vacío y corte como errores tipados) y de AUD-031 (errores saneados; el
    cliente vive mientras dura la petición).
    """

    def __init__(
        self,
        api_key: str,
        client_factory: ClientFactory | None = None,
        budget: LLMBudget | None = None,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self._api_key = api_key
        self._fabrica = client_factory or _cliente_real
        self._budget = budget
        self._max_retries = max_retries
        self.usage: list[UsageRecord] = []

    def _registrar(self, model: str, inicio: float, respuesta: Any) -> None:
        entrada, salida, razonamiento = _uso(respuesta)
        registro = UsageRecord(model, entrada, salida, razonamiento, time.monotonic() - inicio)
        self.usage.append(registro)
        if self._budget is not None:
            self._budget.charge(registro)

    def _antes_de_llamar(self) -> None:
        if self._budget is not None:
            self._budget.check()

    def list_models(self) -> list[ModelInfo]:
        """Modelos que la clave puede usar para generar texto (`models.list`)."""
        with frontera(self._api_key):
            cliente = self._fabrica(self._api_key)  # vivo durante la petición (AUD-031)
            modelos = [
                ModelInfo(
                    id=str(m.name).removeprefix("models/"),
                    display_name=str(getattr(m, "display_name", None) or m.name),
                    input_token_limit=getattr(m, "input_token_limit", None),
                    output_token_limit=getattr(m, "output_token_limit", None),
                )
                for m in cliente.models.list()
                if "generateContent" in (getattr(m, "supported_actions", None) or [])
            ]
        return modelos

    def stream_text(
        self,
        prompt: str,
        *,
        model: str,
        max_output_tokens: int,
        timeout_ms: int,
        system: str | None = None,
    ) -> Iterator[str]:
        """Texto de `generate_content_stream`, trozo a trozo.

        Termina con error tipado si el modelo bloquea, corta o no dice nada.
        """
        config = _build_config(
            timeout_ms=timeout_ms, max_output_tokens=max_output_tokens, system_instruction=system
        )
        for intento in range(self._max_retries + 1):
            self._antes_de_llamar()
            entregado = False
            inicio = time.monotonic()
            ultimo: Any = None
            try:
                with frontera(self._api_key):
                    # El cliente se guarda en una variable a propósito: al destruirse
                    # cierra su transporte HTTP, y como temporal CPython lo destruía
                    # antes de enviar nada. Tiene que vivir hasta agotar el stream.
                    cliente = self._fabrica(self._api_key)
                    respuesta = cliente.models.generate_content_stream(
                        model=model, contents=prompt, config=config
                    )
                    for trozo in respuesta:
                        if getattr(trozo, "usage_metadata", None) is not None:
                            ultimo = trozo
                        texto = _texto(trozo)
                        if texto:
                            entregado = True
                            yield texto
                        _revisar(trozo)
            except GeminiError as exc:
                if ultimo is not None:
                    self._registrar(model, inicio, ultimo)
                if entregado:
                    raise
                _reintentar(intento, exc, self._max_retries)
                continue
            self._registrar(model, inicio, ultimo)
            if not entregado:
                raise GeminiEmpty("El modelo terminó sin devolver texto.")
            return

    def generate_text(
        self,
        prompt: str,
        *,
        model: str,
        max_output_tokens: int,
        timeout_ms: int,
        system: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """Texto completo de `generate_content`, con las mismas garantías."""
        config = _build_config(
            timeout_ms=timeout_ms,
            max_output_tokens=max_output_tokens,
            system_instruction=system,
            temperature=temperature,
        )
        return self._generar(prompt, model=model, config=config)

    def generate_json[T: BaseModel](
        self,
        prompt: str,
        schema: type[T],
        *,
        model: str,
        max_output_tokens: int,
        timeout_ms: int,
        system: str | None = None,
        thinking_budget: int | None = None,
    ) -> T:
        """Una instancia de `schema`, validada.

        Pide la salida estructurada nativa con el JSON Schema del modelo
        Pydantic y valida la respuesta. Si no valida, un único reintento con
        el error en el prompt; si vuelve a fallar, `LLMInvalidJson`.
        """
        config = _build_config(
            timeout_ms=timeout_ms,
            max_output_tokens=max_output_tokens,
            system_instruction=system,
            response_json_schema=schema.model_json_schema(),
            thinking_budget=thinking_budget,
        )
        peticion = prompt
        error = ""
        for _ in range(JSON_ATTEMPTS):
            texto = self._generar(peticion, model=model, config=config)
            try:
                return schema.model_validate_json(texto)
            except ValidationError as exc:
                if _json_cortado(exc):
                    # JSON a medias: con el mismo límite se cortaría otra vez.
                    raise GeminiTruncated("La respuesta JSON llegó incompleta.") from None
                error = str(exc)[:MAX_MESSAGE]
            peticion = (
                f"{prompt}\n\nTu respuesta anterior no cumplía el esquema JSON pedido. "
                f"Error de validación:\n{error}\nDevuelve solo JSON válido según el esquema."
            )
        raise LLMInvalidJson(f"La respuesta no cumple el esquema {schema.__name__}: {error}")

    def _generar(self, prompt: str, *, model: str, config: Any) -> str:
        """Una llamada a `generate_content` con reintentos transitorios y registro."""
        for intento in range(self._max_retries + 1):
            self._antes_de_llamar()
            inicio = time.monotonic()
            try:
                with frontera(self._api_key):
                    cliente = self._fabrica(self._api_key)  # vivo durante la petición
                    respuesta = cliente.models.generate_content(
                        model=model, contents=prompt, config=config
                    )
                    self._registrar(model, inicio, respuesta)
                    _revisar(respuesta)
                    texto = _texto(respuesta)
            except GeminiError as exc:
                _reintentar(intento, exc, self._max_retries)
                continue
            if not texto:
                raise GeminiEmpty("El modelo terminó sin devolver texto.")
            return texto
        raise AssertionError("inalcanzable: el último intento devuelve o relanza")

    def ping(
        self, *, model: str, max_output_tokens: int = 1_024, timeout_ms: int = 30_000
    ) -> None:
        """Comprueba que clave y modelo responden: basta con el primer trozo.

        Sin reintentos ni exigencia de texto: un modelo de razonamiento puede
        gastar el primer trozo pensando, y eso ya demuestra que la clave sirve.
        """
        self._antes_de_llamar()
        config = _build_config(timeout_ms=timeout_ms, max_output_tokens=max_output_tokens)
        inicio = time.monotonic()
        with frontera(self._api_key):
            cliente = self._fabrica(self._api_key)  # vivo durante la petición
            respuesta = cliente.models.generate_content_stream(
                model=model, contents="ping", config=config
            )
            for trozo in respuesta:
                self._registrar(model, inicio, trozo)
                try:
                    _revisar(trozo)
                except GeminiTruncated:
                    pass  # agotar el límite de la prueba no dice nada de la clave
                break
