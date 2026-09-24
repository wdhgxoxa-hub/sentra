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
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

import numpy as np

logger = logging.getLogger(__name__)

# Modelo por defecto: 384 dimensiones, ~130 MB, inferencia ONNX en CPU.
DEFAULT_MODEL_NAME = "BAAI/bge-small-en-v1.5"
DEFAULT_VECTOR_DIM = 384

#: Modelo de la evidencia multifuente (D-M2): multilingüe, ~100 idiomas.
MULTILINGUAL_MODEL_NAME = "intfloat/multilingual-e5-large"
MULTILINGUAL_VECTOR_DIM = 1024

#: Prefijos (consulta, documento) que exige cada modelo. e5 se entrenó con
#: ellos: sin «query: » y «passage: » las búsquedas empeoran sin avisar.
_PREFIJOS: dict[str, tuple[str, str]] = {
    MULTILINGUAL_MODEL_NAME: ("query: ", "passage: "),
}

# Dimension del degradado por hash. Independiente del modelo real.
HASH_FALLBACK_DIM = 128


class EmbeddingError(RuntimeError):
    """No hay ningun proveedor de embeddings semanticos disponible."""


@runtime_checkable
class TextEmbedder(Protocol):
    """Contrato minimo que debe cumplir cualquier proveedor."""

    dim: int
    is_semantic: bool

    def embed_text(self, text: str) -> list[float]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]: ...


def _l2_normalize(vec: np.ndarray) -> list[float]:
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

    def embed_text(self, text: str) -> list[float]:
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

    def embed_query(self, text: str) -> list[float]:
        """Sin prefijos: el hash no distingue consultas de documentos."""
        return self.embed_text(text)

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


#: B2: pooling de e5 fijado de forma explícita. fastembed 0.8.0 pasó
#: intfloat/multilingual-e5-large de CLS a mean pooling y avisaba en cada carga.
#: Verificado en su código: PooledEmbedding hace mean_pooling y los vectores ya
#: guardados (evidence_e5) salieron de esa versión. Se registra un modelo propio
#: con el mismo ONNX, mean pooling y normalización: mismos vectores, sin depender
#: del valor por defecto de la biblioteca.
E5_POOLING = "mean"
E5_MEAN_MODEL_NAME = "sentra/multilingual-e5-large-mean"
E5_ONNX_REPO = "qdrant/multilingual-e5-large-onnx"
_REGISTRADOS: set[str] = set()


def _nombre_fastembed(model_name: str) -> str:
    """El nombre con el que se carga en fastembed (e5: el registro propio con pooling fijo)."""
    if model_name != MULTILINGUAL_MODEL_NAME:
        return model_name
    if E5_MEAN_MODEL_NAME not in _REGISTRADOS:
        from fastembed import TextEmbedding
        from fastembed.common.model_description import ModelSource, PoolingType

        try:
            TextEmbedding.add_custom_model(
                model=E5_MEAN_MODEL_NAME, pooling=PoolingType.MEAN, normalization=True,
                sources=ModelSource(hf=E5_ONNX_REPO), dim=MULTILINGUAL_VECTOR_DIM,
                model_file="model.onnx", additional_files=["model.onnx_data"],
                description="intfloat/multilingual-e5-large con mean pooling explícito",
                license="mit", size_in_gb=2.24,
            )
        except ValueError:
            pass  # ya registrado en este proceso por otra instancia
        _REGISTRADOS.add(E5_MEAN_MODEL_NAME)
    return E5_MEAN_MODEL_NAME


class FastEmbedEmbedder:
    """
    Proveedor semantico real sobre fastembed (onnxruntime).

    La primera instanciacion descarga el modelo a la cache local; a partir
    de ahi funciona sin red.
    """

    is_semantic = True

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME, _modelo: Any = None) -> None:
        """`_modelo` sustituye a fastembed en los tests (sin descargar nada)."""
        if _modelo is not None:
            self._model = _modelo
        else:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:
                raise EmbeddingError(
                    "fastembed no esta instalado. Instalalo con 'pip install fastembed' "
                    "o pide explicitamente el degradado con "
                    "get_embedder(allow_hash_fallback=True)."
                ) from exc

            try:
                from core.rutas import ruta_modelos

                self._model = TextEmbedding(model_name=_nombre_fastembed(model_name),
                                            cache_dir=str(ruta_modelos()))
            except Exception as exc:
                raise EmbeddingError(
                    f"No se pudo inicializar el modelo '{model_name}': {exc}"
                ) from exc

        self._prefijo_consulta, self._prefijo_documento = _PREFIJOS.get(model_name, ("", ""))
        self.model_name = model_name
        self.name = f"fastembed:{model_name}"
        self.dim = len(self.embed_text("dimension probe"))

    def embed_text(self, text: str) -> list[float]:
        """Vector de un documento (con el prefijo de documento del modelo)."""
        return self.embed_batch([text])[0]

    def embed_query(self, text: str) -> list[float]:
        """Vector de una consulta (con el prefijo de consulta del modelo)."""
        return self._embed([self._prefijo_consulta + text])[0]

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Vectores de documentos."""
        return self._embed([self._prefijo_documento + t for t in texts])

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [
            _l2_normalize(np.asarray(vec, dtype=np.float32))
            for vec in self._model.embed(texts)
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
