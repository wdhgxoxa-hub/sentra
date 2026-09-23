"""
Deduplicación entre fuentes (F2.6)
==================================

El mismo texto publicado en varias plataformas no es corroboración: si
contara, un solo autor que crosspostea inflaría la convergencia entre
fuentes (G1) y podría producir un falso CONSTRUIR, el peor error posible.

Dos etapas:
1. Huella del texto normalizado (`content_fingerprint`): copia literal.
2. Similitud de embeddings ≥ CROSSPOST_MIN_SIMILARITY, solo en textos de
   al menos MIN_CHARS_FOR_SEMANTIC_DEDUP caracteres: copia retocada.

Se conserva el ítem más antiguo (el original) y se anotan los demás.
Recorrido codicioso por fecha: cada ítem se compara con los canónicos ya
elegidos, no con los duplicados, así que a≈b y b≈c no funden a c con a.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from core.evidence.model import EvidenceItem, content_fingerprint

#: Coseno mínimo (e5-large) para tratar dos textos como el mismo publicado
#: dos veces. Una copia con retoques (un enlace, otro formato) queda por
#: encima de 0,97; quejas independientes del mismo problema suelen quedar
#: entre 0,80 y 0,93. 0,95 separa las dos: fundir quejas distintas borraría
#: corroboración real, y no fundir copias la inflaría.
CROSSPOST_MIN_SIMILARITY = 0.95

#: Los textos cortos («same here, so annoying») se parecen mucho entre sí
#: aunque los escriban personas distintas: por debajo de este largo solo se
#: funden si son idénticos.
MIN_CHARS_FOR_SEMANTIC_DEDUP = 80


@dataclass(frozen=True)
class Duplicate:
    duplicate_id: str
    canonical_id: str
    method: Literal["fingerprint", "embedding"]
    similarity: float | None


@dataclass
class DedupResult:
    canonical: list[EvidenceItem] = field(default_factory=list)
    duplicates: list[Duplicate] = field(default_factory=list)


def _unitario(vector: Sequence[float]) -> np.ndarray:
    v = np.asarray(vector, dtype=np.float32)
    norma = float(np.linalg.norm(v))
    return v / norma if norma else v


def deduplicate(
    items: Sequence[EvidenceItem], vectors: Mapping[str, Sequence[float]]
) -> DedupResult:
    """Canónicos (el más antiguo de cada grupo) y duplicados anotados."""
    resultado = DedupResult()
    por_huella: dict[str, str] = {}
    semanticos: list[tuple[str, np.ndarray]] = []

    for item in sorted(items, key=lambda i: (i.created_at, i.id)):
        huella = content_fingerprint(item.text)
        if huella in por_huella:
            resultado.duplicates.append(
                Duplicate(item.id, por_huella[huella], "fingerprint", None))
            continue

        vector = vectors.get(item.id)
        largo = len(item.text.strip()) >= MIN_CHARS_FOR_SEMANTIC_DEDUP
        if vector is not None and largo and semanticos:
            actual = _unitario(vector)
            matriz = np.stack([v for _, v in semanticos])
            similitudes = matriz @ actual
            mejor = int(np.argmax(similitudes))
            if float(similitudes[mejor]) >= CROSSPOST_MIN_SIMILARITY:
                resultado.duplicates.append(Duplicate(
                    item.id, semanticos[mejor][0], "embedding",
                    round(float(similitudes[mejor]), 4)))
                continue

        resultado.canonical.append(item)
        por_huella[huella] = item.id
        if vector is not None and largo:
            semanticos.append((item.id, _unitario(vector)))
    return resultado
