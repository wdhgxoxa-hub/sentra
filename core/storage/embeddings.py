"""
Proveedores de Embeddings (Politica de Calidad Vectorial)
=========================================================

Este modulo existe para separar dos cosas que antes estaban mezcladas:

1. Un embedder REAL, semantico, capaz de acercar parafrasis en el espacio
   vectorial (`FastEmbedEmbedder`, ONNX, sin PyTorch).
2. Un embedder de EMERGENCIA, `HashEmbedder`, que proyecta terminos por
   hash MD5. Es determinista y no necesita descargas, pero NO es semantico:
   dos formas distintas de decir lo mismo caen en dimensiones ortogonales.

Regla de oro: el `HashEmbedder` nunca se activa solo. `get_embedder()` falla
con `EmbeddingError` si no hay proveedor real, salvo que quien llama pida el
degradado de forma explicita con `allow_hash_fallback=True`. Un buscador
semantico que en realidad no lo es resulta mucho peor que un error.
"""

from __future__ import annotations

import hashlib
import logging
from typing import List, Protocol, Sequence, runtime_checkable

import numpy as np

logger = logging.getLogger(__name__)

# Modelo por defecto: 384 dimensiones, ~130 MB, inferencia ONNX en CPU.
DEFAULT_MODEL_NAME = "BAAI/bge-small-en-v1.5"
DEFAULT_VECTOR_DIM = 384

# Dimension del degradado por hash. Independiente del modelo real.
HASH_FALLBACK_DIM = 128


class EmbeddingError(RuntimeError):
    """No hay ningun proveedor de embeddings semanticos disponible."""


@runtime_checkable
class TextEmbedder(Protocol):
    """Contrato minimo que debe cumplir cualquier proveedor."""

    dim: int
    is_semantic: bool

    def embed_text(self, text: str) -> List[float]: ...

    def embed_batch(self, texts: Sequence[str]) -> List[List[float]]: ...


def _l2_normalize(vec: np.ndarray) -> List[float]:
    """Devuelve el vector con norma unitaria (o de ceros si el original lo era)."""
    norm = float(np.linalg.norm(vec))
    if norm > 0.0:
        vec = vec / norm
    return [float(v) for v in vec]


class HashEmbedder:
    """
    Degradado de emergencia: proyeccion por hashing con signo sobre `dim`
    dimensiones, L2-normalizada.

    NO es semantico. Solo sirve para mantener el sistema en pie (o para
    pruebas rapidas y deterministas) cuando no hay un modelo real a mano.
    """

    is_semantic = False
    name = "hash-md5"

    def __init__(self, dim: int = HASH_FALLBACK_DIM) -> None:
        if dim <= 0:
            raise ValueError("La dimension debe ser un entero positivo")
        self.dim = dim

    def embed_text(self, text: str) -> List[float]:
        vec = np.zeros(self.dim, dtype=np.float32)
        words = text.lower().split()
        if not words:
            return [0.0] * self.dim

        for word in words:
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if ((h >> 8) & 1) else -1.0
            vec[idx] += sign

        return _l2_normalize(vec)

    def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]


class FastEmbedEmbedder:
    """
    Proveedor semantico real sobre fastembed (onnxruntime).

    La primera instanciacion descarga el modelo a la cache local; a partir
    de ahi funciona sin red.
    """

    is_semantic = True

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise EmbeddingError(
                "fastembed no esta instalado. Instalalo con 'pip install fastembed' "
                "o pide explicitamente el degradado con "
                "get_embedder(allow_hash_fallback=True)."
            ) from exc

        try:
            self._model = TextEmbedding(model_name=model_name)
        except Exception as exc:
            raise EmbeddingError(
                f"No se pudo inicializar el modelo '{model_name}': {exc}"
            ) from exc

        self.model_name = model_name
        self.name = f"fastembed:{model_name}"
        self.dim = len(self.embed_text("dimension probe"))

    def embed_text(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        return [
            _l2_normalize(np.asarray(vec, dtype=np.float32))
            for vec in self._model.embed(list(texts))
        ]


def get_embedder(
    allow_hash_fallback: bool = False,
    model_name: str = DEFAULT_MODEL_NAME,
    _force_unavailable: bool = False,
) -> TextEmbedder:
    """
    Devuelve el mejor proveedor disponible.

    Args:
        allow_hash_fallback: activa el degradado NO semantico por hash. Es una
            decision consciente de quien llama; por defecto se prefiere fallar.
        model_name: modelo de fastembed a cargar.
        _force_unavailable: unicamente para pruebas; simula que no hay ningun
            proveedor real instalado.

    Raises:
        EmbeddingError: si no hay proveedor real y no se acepto el degradado.
    """
    if not _force_unavailable:
        try:
            return FastEmbedEmbedder(model_name=model_name)
        except EmbeddingError as exc:
            logger.warning("Proveedor semantico no disponible: %s", exc)

    if allow_hash_fallback:
        logger.warning(
            "EMBEDDINGS DEGRADADOS: se usara HashEmbedder, que NO es semantico. "
            "La busqueda vectorial solo encontrara coincidencias lexicas."
        )
        return HashEmbedder(dim=HASH_FALLBACK_DIM)

    raise EmbeddingError(
        "No hay proveedor de embeddings semanticos disponible. Instala fastembed "
        "('pip install fastembed') o acepta explicitamente el degradado con "
        "get_embedder(allow_hash_fallback=True)."
    )
