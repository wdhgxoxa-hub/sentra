"""Lo común a cualquier proveedor de modelos de lenguaje."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


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
