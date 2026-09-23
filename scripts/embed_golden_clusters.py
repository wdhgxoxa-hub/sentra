"""Calcula los vectores e5 del conjunto dorado de agrupación (B3).

    python scripts/embed_golden_clusters.py

Escribe tests/fixtures/golden_clusters_e5.npz con los ids, los vectores y el
modelo y pooling que los produjeron. Los tests de calibración leen ese
fichero (no cargan el modelo de 2,24 GB) y comprueban que sus metadatos
siguen coincidiendo con el código. Volver a ejecutarlo solo si cambia el
conjunto dorado, el modelo o el pooling.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.storage.embeddings import (
    E5_POOLING,
    MULTILINGUAL_MODEL_NAME,
    FastEmbedEmbedder,
)

DORADO = RAIZ / "tests" / "fixtures" / "golden_clusters.json"
SALIDA = RAIZ / "tests" / "fixtures" / "golden_clusters_e5.npz"


def main() -> None:
    conjunto = json.loads(DORADO.read_text(encoding="utf-8"))
    items = conjunto["items"]
    embebedor = FastEmbedEmbedder(MULTILINGUAL_MODEL_NAME)
    vectores = np.asarray(embebedor.embed_batch([i["text"] for i in items]), dtype=np.float32)
    np.savez_compressed(
        SALIDA, ids=np.asarray([i["id"] for i in items]), vectors=vectores,
        model=np.asarray(MULTILINGUAL_MODEL_NAME), pooling=np.asarray(E5_POOLING),
        golden_version=np.asarray(conjunto["version"]))
    print(f"{len(items)} vectores de {vectores.shape[1]} dimensiones en {SALIDA.name}")


if __name__ == "__main__":
    main()
