"""Lo común a cualquier proveedor de modelos de lenguaje."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class LLMError(RuntimeError):
    """Fallo del motor de IA. Su mensaje ya está saneado.

    `code` es estable y lo traduce la interfaz; `transient` dice si merece
    la pena reintentar; `missing` lo usan los errores de estructura
    incompleta.
    """

    code = "llm_error"
    transient = False

    def __init__(self, detail: str, *, missing: Sequence[str] = ()) -> None:
        super().__init__(detail)
        self.missing = list(missing)


class LLMModelUnavailable(LLMError):
    """El modelo pedido no está entre los que la clave puede usar."""

    code = "llm_model_unavailable"


@dataclass(frozen=True)
class ModelInfo:
    """Un modelo que la clave puede usar para generar texto."""

    id: str
    display_name: str
    input_token_limit: int | None
    output_token_limit: int | None


class LLMInvalidJson(LLMError):
    """La respuesta no cumplió el esquema ni tras el reintento con el error."""

    code = "llm_invalid_json"


class LLMTruncated(LLMError):
    """La respuesta se cortó al agotar el límite de salida (o llegó JSON a medias).

    En Gemini 3.x el razonamiento cuenta dentro de ese límite. Reintentar con el
    mismo límite se volvería a cortar: quien llama decide (p. ej. partir el lote).
    """

    code = "llm_truncated"


class LLMBudgetExhausted(LLMError):
    """Se agotó el presupuesto de tokens del escaneo: la llamada no sale."""

    code = "llm_budget_exhausted"


@dataclass(frozen=True)
class UsageRecord:
    """Lo que costó una llamada. None = el proveedor no lo informó (no es 0)."""

    model: str
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    duration_s: float

    @property
    def total_tokens(self) -> int:
        return sum(t or 0 for t in (self.input_tokens, self.output_tokens, self.reasoning_tokens))


@runtime_checkable
class LLMProvider(Protocol):
    """Lo que el resto de SENTRA puede pedirle a un modelo de lenguaje.

    Parámetros neutros: la configuración propia del proveedor (la del SDK)
    se construye dentro. `usage` acumula un `UsageRecord` por llamada.
    """

    usage: list[UsageRecord]

    def list_models(self) -> list[ModelInfo]: ...

    def generate_text(
        self,
        prompt: str,
        *,
        model: str,
        max_output_tokens: int,
        timeout_ms: int,
        system: str | None = None,
        temperature: float | None = None,
    ) -> str: ...

    def stream_text(
        self,
        prompt: str,
        *,
        model: str,
        max_output_tokens: int,
        timeout_ms: int,
        system: str | None = None,
    ) -> Iterator[str]: ...

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
    ) -> T: ...

    def ping(self, *, model: str) -> None: ...
