"""
Juez, etapa 2: agrupación multifuente
=====================================

Agrupamiento «líder» voraz y determinista sobre embeddings multilingües
(e5-large, D-M2): los ítems se recorren por fecha y cada uno se une al
grupo cuyo centroide supera CLUSTER_MIN_SIMILARITY, o abre uno nuevo. La
misma queja en inglés y en español cae en el mismo grupo si sus vectores
están cerca; el idioma no separa.

Solo los grupos con al menos MIN_CLUSTER_SIZE miembros llegan al juez.
La identidad es estable entre escaneos (D-G): un grupo que comparte
miembros o palabras clave con una lectura anterior hereda su UUID; uno
nuevo recibe un UUID determinista (uuid5 de sus miembros).
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from core.evidence.model import EvidenceItem
from core.storage.identity import Candidato, Previo, asignar_identidades

#: Coseno mínimo con el centroide para unirse a un grupo. PROVISIONAL: e5 comprime
#: los cosenos (temas ajenos ~0,75, paráfrasis ~0,9); se revisa con el escaneo real.
CLUSTER_MIN_SIMILARITY = 0.86
#: Por debajo, un grupo es ruido y no llega al juez.
MIN_CLUSTER_SIZE = 3
KEYWORDS_PER_CLUSTER = 5
_NAMESPACE = uuid.UUID("5e27a000-0000-4000-8000-000000000f03")

_PALABRA = re.compile(r"[a-záéíóúüñ]{3,}")
STOPWORDS = frozenset(["the", "and", "for", "that", "this", "with", "you", "your", "are", "was", "were", "have", "has", "had", "not", "but", "can", "all", "any", "our", "out", "its", "it's", "they", "them", "their", "there", "what", "when", "which", "who", "why", "how", "just", "like", "from", "into", "about", "than", "then", "too", "very", "also", "only", "some", "such", "more", "most", "other", "been", "being", "does", "did", "doing", "would", "could", "should", "will", "shall", "may", "might", "must", "one", "two", "get", "got", "make", "made", "every", "each", "much", "many", "per", "los", "las", "del", "por", "para", "con", "una", "unos", "unas", "que", "qué", "como", "cómo", "pero", "sus", "mis", "tus", "nos", "este", "esta", "estos", "estas", "ese", "esa", "eso", "aquí", "allí", "más", "menos", "muy", "sin", "sobre", "entre", "cada", "todo", "toda", "todos", "todas", "hay", "han", "has", "hace", "hago", "mes", "año", "también", "porque", "cuando", "donde", "quien", "cual", "algo", "alguna", "alguno"])


@dataclass
class EvidenceCluster:
    key: str
    opportunity_id: str
    member_ids: list[str]
    keywords: list[str]
    centroid: list[float] = field(repr=False)


def _unitario(vector: Sequence[float]) -> np.ndarray:
    v = np.asarray(vector, dtype=np.float64)
    norma = float(np.linalg.norm(v))
    return v / norma if norma else v


def _palabras_clave(textos: Sequence[str]) -> list[str]:
    conteo: Counter[str] = Counter()
    for texto in textos:
        conteo.update({p for p in _PALABRA.findall(texto.casefold()) if p not in STOPWORDS})
    return [p for p, _ in sorted(conteo.items(), key=lambda kv: (-kv[1], kv[0]))][:KEYWORDS_PER_CLUSTER]


def cluster_evidence(
    items: Sequence[EvidenceItem],
    vectors: Mapping[str, Sequence[float]],
    *,
    previous: Sequence[Previo] = (),
) -> list[EvidenceCluster]:
    """Grupos de al menos MIN_CLUSTER_SIZE ítems, con identidad estable."""
    grupos: list[tuple[list[EvidenceItem], list[np.ndarray]]] = []
    for item in sorted(items, key=lambda i: (i.created_at, i.id)):
        vector = vectors.get(item.id)
        if vector is None:
            continue
        actual = _unitario(vector)
        mejor, similitud = None, CLUSTER_MIN_SIMILARITY
        for indice, (_, vs) in enumerate(grupos):
            coseno = float(_unitario(np.mean(vs, axis=0)) @ actual)
            if coseno >= similitud:
                mejor, similitud = indice, coseno
        if mejor is None:
            grupos.append(([item], [actual]))
        else:
            grupos[mejor][0].append(item)
            grupos[mejor][1].append(actual)

    candidatos: list[tuple[Candidato, list[EvidenceItem], np.ndarray]] = []
    for miembros, vs in grupos:
        if len(miembros) < MIN_CLUSTER_SIZE:
            continue
        palabras = _palabras_clave([m.text for m in miembros])
        ids = sorted(m.id for m in miembros)
        clave = "-".join(palabras[:3]) or ids[0]
        candidatos.append((Candidato(clave=f"{clave}#{ids[0]}", miembros=set(ids),
                                     palabras=set(palabras)), miembros,
                           _unitario(np.mean(vs, axis=0))))

    heredados = asignar_identidades([c for c, _, _ in candidatos], previous)
    resultado = []
    for candidato, miembros, centroide in candidatos:
        ids = sorted(candidato.miembros)
        nuevo = str(uuid.uuid5(_NAMESPACE, ",".join(ids)))
        resultado.append(EvidenceCluster(
            key=candidato.clave, opportunity_id=heredados.get(candidato.clave) or nuevo,
            member_ids=ids, keywords=_palabras_clave([m.text for m in miembros]),
            centroid=[float(x) for x in centroide]))
    return sorted(resultado, key=lambda g: g.key)
