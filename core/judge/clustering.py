"""
Juez, etapa 2: agrupación multifuente
=====================================

clustering-v2 (B3): enlace promedio jerárquico sobre embeddings
multilingües (e5-large, D-M2), con umbral CLUSTER_MIN_SIMILARITY elegido por
pureza y ARI en un conjunto dorado. La misma queja en inglés y en español
cae en el mismo grupo si sus vectores están cerca; el idioma no separa.
clustering-v1 (líder voraz) queda como leader_partition, para el barrido.

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

#: B3: elegido por métrica sobre el conjunto dorado de agrupación
#: (tests/fixtures/golden_clusters.json; barrido en scripts/calibrar_agrupacion.py):
#: enlace promedio con 0,82 dio pureza 0,735 y ARI 0,487 (6 grupos), frente a
#: ARI 0,206 del líder con 0,86 de clustering-v1, que mezclaba subproblemas.
#: v3 (AUD2-001): solo agrupa evidencia con dolor pertinente y el tema del
#: escaneo no nombra nichos. El método y el umbral son los de v2.
CLUSTERING_VERSION = "clustering-v3"
CLUSTERING_METHOD = "average_linkage"
CLUSTER_MIN_SIMILARITY = 0.82
#: Por debajo, un grupo es ruido y no llega al juez.
MIN_CLUSTER_SIZE = 3
KEYWORDS_PER_CLUSTER = 5
_NAMESPACE = uuid.UUID("5e27a000-0000-4000-8000-000000000f03")

_PALABRA = re.compile(r"[a-záéíóúüñ]{3,}")
#: Enlaces y contracciones inglesas se quitan antes de contar (AUD2-006): de
#: «https://github.com/…» salían «https», «com» y «github», y de «don't», «don».
_URL = re.compile(r"(?:https?://|www\.)\S+")
_CONTRACCION = re.compile(r"\b[a-z]+['’](?:t|s|re|ve|ll|d|m)\b")
#: Etiquetas de formato de Hacker News («Show HN:», «Ask HN:»…): no nombran nichos.
_ETIQUETA_HN = re.compile(r"\b(?:show|ask|launch|tell)\s+hn\b")
STOPWORDS = frozenset([
    "the", "and", "for", "that", "this", "with", "you", "your", "are", "was", "were", "have",
    "has", "had", "not", "but", "can", "all", "any", "our", "out", "its", "it's", "they",
    "them", "their", "there", "what", "when", "which", "who", "why", "how", "just", "like",
    "from", "into", "about", "than", "then", "too", "very", "also", "only", "some", "such",
    "more", "most", "other", "been", "being", "does", "did", "doing", "would", "could",
    "should", "will", "shall", "may", "might", "must", "one", "two", "get", "got", "make",
    "made", "every", "each", "much", "many", "per", "los", "las", "del", "por", "para", "con",
    "una", "unos", "unas", "que", "qué", "como", "cómo", "pero", "sus", "mis", "tus", "nos",
    "este", "esta", "estos", "estas", "ese", "esa", "eso", "aquí", "allí", "más", "menos",
    "muy", "sin", "sobre", "entre", "cada", "todo", "toda", "todos", "todas", "hay", "han",
    "has", "hace", "hago", "mes", "año", "también", "porque", "cuando", "donde", "quien",
    "cual", "algo", "alguna", "alguno",
    # Relleno de alta frecuencia que no nombra ningún problema (AUD2-006).
    "where", "after", "before", "actually", "really", "want", "wanted", "need", "needs",
    "built", "build", "building", "see", "seen", "again", "still", "even", "well", "know",
    "think", "thing", "things", "way", "lot", "something", "anything", "anyone", "someone",
    "here", "now", "new", "use", "used", "using", "going", "able", "sure", "yes", "yet",
    "these", "those", "while", "since", "because", "though", "without", "within", "over",
    "under", "back", "off", "down", "same", "own", "both", "few", "less", "never", "always",
    "time", "day", "days", "year", "years", "hey", "thanks", "hola", "gracias", "ahora",
])


@dataclass
class EvidenceCluster:
    key: str
    opportunity_id: str
    member_ids: list[str]
    keywords: list[str]
    centroid: list[float] = field(repr=False)


def _unitario(vector: Sequence[float] | np.ndarray) -> np.ndarray:
    v = np.asarray(vector, dtype=np.float64)
    norma = float(np.linalg.norm(v))
    return v / norma if norma else v


def _palabras_clave(textos: Sequence[str], excluir: Sequence[str] = ()) -> list[str]:
    """Las más frecuentes del grupo; `excluir` son los términos del tema del
    escaneo, que están en todos los grupos y no distinguen ninguno."""
    vacias = STOPWORDS | {p for termino in excluir for p in _PALABRA.findall(termino.casefold())}
    conteo: Counter[str] = Counter()
    for texto in textos:
        limpio = _ETIQUETA_HN.sub(" ", _CONTRACCION.sub(" ", _URL.sub(" ", texto.casefold())))
        conteo.update({p for p in _PALABRA.findall(limpio) if p not in vacias})
    return [p for p, _ in sorted(conteo.items(), key=lambda kv: (-kv[1], kv[0]))][:KEYWORDS_PER_CLUSTER]


def leader_partition(vectores: Sequence[Sequence[float]], umbral: float) -> list[int]:
    """Líder voraz (clustering-v1): cada vector, en orden, al grupo cuyo
    centroide más se le parece si supera `umbral`; si no, abre uno."""
    etiquetas: list[int] = []
    grupos: list[list[np.ndarray]] = []
    for vector in vectores:
        actual = _unitario(vector)
        mejor, similitud = None, umbral
        for indice, vs in enumerate(grupos):
            coseno = float(_unitario(np.mean(vs, axis=0)) @ actual)
            if coseno >= similitud:
                mejor, similitud = indice, coseno
        if mejor is None:
            grupos.append([actual])
            etiquetas.append(len(grupos) - 1)
        else:
            grupos[mejor].append(actual)
            etiquetas.append(mejor)
    return etiquetas


def average_linkage_partition(vectores: Sequence[Sequence[float]], umbral: float) -> list[int]:
    """Enlace promedio (jerárquico aglomerativo): se unen los dos grupos cuya
    similitud media entre pares es la mayor, mientras sea >= `umbral`. No
    encadena como el enlace mínimo; empates, por el par de índices menor.

    Actualización de Lance-Williams: la similitud media de (a ∪ b) con c es
    (|a|·s(a,c) + |b|·s(b,c)) / (|a| + |b|). O(n²) por unión, vectorizada.
    """
    n = len(vectores)
    if n == 0:
        return []
    matriz = np.stack([_unitario(v) for v in vectores])
    similitud = matriz @ matriz.T
    np.fill_diagonal(similitud, -np.inf)
    tamanos = np.ones(n)
    vivos = np.ones(n, dtype=bool)
    miembros: list[list[int]] = [[i] for i in range(n)]
    while vivos.sum() > 1:
        activa = np.where(vivos[:, None] & vivos[None, :], similitud, -np.inf)
        a, b = divmod(int(np.argmax(np.triu(activa, k=1) + np.tril(np.full((n, n), -np.inf)))), n)
        if activa[a, b] < umbral:
            break
        nueva = (tamanos[a] * similitud[a] + tamanos[b] * similitud[b]) / (tamanos[a] + tamanos[b])
        similitud[a, :] = nueva
        similitud[:, a] = nueva
        similitud[a, a] = -np.inf
        tamanos[a] += tamanos[b]
        vivos[b] = False
        miembros[a] = sorted(miembros[a] + miembros[b])
    etiquetas = [0] * n
    for numero, grupo in enumerate(sorted(miembros[i] for i in range(n) if vivos[i])):
        for i in grupo:
            etiquetas[i] = numero
    return etiquetas


def cluster_evidence(
    items: Sequence[EvidenceItem],
    vectors: Mapping[str, Sequence[float]],
    *,
    previous: Sequence[Previo] = (),
    excluir: Sequence[str] = (),
) -> list[EvidenceCluster]:
    """Grupos de al menos MIN_CLUSTER_SIZE ítems, con identidad estable."""
    con_vector = [i for i in sorted(items, key=lambda i: (i.created_at, i.id)) if i.id in vectors]
    etiquetas = average_linkage_partition([vectors[i.id] for i in con_vector],
                                          CLUSTER_MIN_SIMILARITY)
    por_etiqueta: dict[int, tuple[list[EvidenceItem], list[np.ndarray]]] = {}
    for item, etiqueta in zip(con_vector, etiquetas, strict=True):
        miembros, vs = por_etiqueta.setdefault(etiqueta, ([], []))
        miembros.append(item)
        vs.append(_unitario(vectors[item.id]))
    grupos = [por_etiqueta[e] for e in sorted(por_etiqueta)]

    candidatos: list[tuple[Candidato, list[EvidenceItem], np.ndarray]] = []
    for miembros, vs in grupos:
        if len(miembros) < MIN_CLUSTER_SIZE:
            continue
        palabras = _palabras_clave([m.text for m in miembros], excluir)
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
            member_ids=ids, keywords=_palabras_clave([m.text for m in miembros], excluir),
            centroid=[float(x) for x in centroide]))
    return sorted(resultado, key=lambda g: g.key)
