"""
Módulo de Clustering Semántico y Descubrimiento de Tópicos Emergentes
====================================================================
Extraído y adaptado de reddit-nlp-analytics (app/services/nlp_service.py).

Proporciona:
1. Agrupación no supervisada de publicaciones y comentarios en clústeres temáticos.
2. Extracción de palabras clave emergentes (unigramas y bigramas) mediante TF-IDF adaptativo.
3. Identificación de problemas novedosos o quejas no contempladas en diccionarios estáticos.
4. Selección del texto más representativo de cada clúster mediante proximidad a los centroides.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import numpy as np
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TopicCluster(BaseModel):
    """Clúster temático descubierto con sus palabras clave y texto más representativo."""
    cluster_id: int
    label: str
    top_keywords: list[str] = Field(default_factory=list)
    size: int
    percentage: float
    representative_text: str
    member_indices: list[int] = Field(default_factory=list)


class ClusteringResult(BaseModel):
    """Resultado consolidado del análisis de clustering temático."""
    total_documents: int
    n_clusters: int
    clusters: list[TopicCluster] = Field(default_factory=list)
    global_top_keywords: list[str] = Field(default_factory=list)


class TopicClusterer:
    """
    Motor de descubrimiento no supervisado de tópicos emergentes y clústeres de dolor.
    """

    def __init__(
        self,
        max_features: int = 1500,
        ngram_range: tuple[int, int] = (1, 2),
        min_df: int = 1,
        random_state: int = 42
    ) -> None:
        self.max_features = max_features
        self.ngram_range = ngram_range
        self.min_df = min_df
        self.random_state = random_state

    def extract_emerging_keywords(
        self,
        texts: Sequence[str],
        top_n: int = 15
    ) -> list[tuple[str, float]]:
        """
        Extrae los términos y colocaciones (bigramas) con mayor peso TF-IDF en el corpus.
        Permite detectar quejas o nombres de herramientas emergentes.
        """
        if not texts:
            return []

        from sklearn.feature_extraction.text import TfidfVectorizer

        valid_texts = [t.strip() for t in texts if t and len(t.strip()) > 10]
        if not valid_texts:
            return []

        vectorizer = TfidfVectorizer(
            ngram_range=self.ngram_range,
            max_features=self.max_features,
            stop_words="english",
            min_df=self.min_df,
            sublinear_tf=True
        )

        try:
            tfidf_matrix = vectorizer.fit_transform(valid_texts)
            feature_names = np.array(vectorizer.get_feature_names_out())
            mean_tfidf = np.asarray(tfidf_matrix.mean(axis=0)).ravel()

            top_indices = mean_tfidf.argsort()[::-1][:top_n]
            return [
                (str(feature_names[i]), round(float(mean_tfidf[i]), 4))
                for i in top_indices
            ]
        except Exception as e:
            logger.error(f"Error extrayendo palabras clave emergentes: {e}")
            return []

    def cluster(
        self,
        texts: Sequence[str],
        n_clusters: int | None = None,
        top_keywords_per_cluster: int = 5
    ) -> ClusteringResult:
        """
        Agrupa los textos en clústeres semánticos utilizando TF-IDF y K-Means.
        Identifica automáticamente la etiqueta representativa y las palabras clave de cada clúster.
        """
        from sklearn.cluster import KMeans
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import pairwise_distances_argmin_min

        clean_texts = [t.strip() for t in texts]
        non_empty_indices = [i for i, t in enumerate(clean_texts) if len(t) > 5]

        if len(non_empty_indices) < 2:
            # No hay suficientes datos para clustering
            single_text = clean_texts[0] if clean_texts else ""
            cluster_obj = TopicCluster(
                cluster_id=0,
                label="General",
                top_keywords=[],
                size=len(clean_texts),
                percentage=100.0,
                representative_text=single_text[:200],
                member_indices=list(range(len(clean_texts)))
            )
            return ClusteringResult(
                total_documents=len(clean_texts),
                n_clusters=1,
                clusters=[cluster_obj],
                global_top_keywords=[]
            )

        # Ajustar n_clusters según el tamaño de muestra si no se especifica
        if n_clusters is None:
            n_clusters = min(max(2, len(non_empty_indices) // 4), 6)
        n_clusters = min(n_clusters, len(non_empty_indices))

        filtered_corpus = [clean_texts[i] for i in non_empty_indices]

        vectorizer = TfidfVectorizer(
            ngram_range=self.ngram_range,
            max_features=self.max_features,
            stop_words="english",
            min_df=self.min_df,
            sublinear_tf=True
        )

        tfidf_matrix = vectorizer.fit_transform(filtered_corpus)
        feature_names = np.array(vectorizer.get_feature_names_out())

        kmeans = KMeans(
            n_clusters=n_clusters,
            random_state=self.random_state,
            n_init=10
        )
        labels = kmeans.fit_predict(tfidf_matrix)

        # Encontrar los textos más cercanos a los centroides (representativos)
        closest_indices, _ = pairwise_distances_argmin_min(kmeans.cluster_centers_, tfidf_matrix)

        # Palabras globales emergentes
        global_keywords = [kw for kw, _ in self.extract_emerging_keywords(filtered_corpus, top_n=10)]

        clusters_output: list[TopicCluster] = []

        for cid in range(n_clusters):
            # Índices de miembros en filtered_corpus y mapeados a los índices originales
            cluster_filtered_idx = np.where(labels == cid)[0]
            cluster_orig_indices = [non_empty_indices[idx] for idx in cluster_filtered_idx]
            size = len(cluster_orig_indices)
            percentage = round((size / len(clean_texts)) * 100.0, 2)

            # Extraer las palabras clave con mayor peso en el centroide del clúster
            centroid = kmeans.cluster_centers_[cid]
            top_kw_idx = centroid.argsort()[::-1][:top_keywords_per_cluster]
            top_kws = [str(feature_names[i]) for i in top_kw_idx if centroid[i] > 0]

            # Etiqueta generada a partir de las dos palabras clave más fuertes
            cluster_label = " + ".join(top_kws[:2]).title() if top_kws else f"Clúster {cid + 1}"

            # Texto representativo más próximo al centroide
            rep_filtered_idx = closest_indices[cid]
            rep_text = filtered_corpus[rep_filtered_idx][:300].strip()

            clusters_output.append(
                TopicCluster(
                    cluster_id=cid,
                    label=cluster_label,
                    top_keywords=top_kws,
                    size=size,
                    percentage=percentage,
                    representative_text=rep_text,
                    member_indices=cluster_orig_indices
                )
            )

        # Ordenar clústeres por tamaño decreciente
        clusters_output.sort(key=lambda c: c.size, reverse=True)

        return ClusteringResult(
            total_documents=len(clean_texts),
            n_clusters=n_clusters,
            clusters=clusters_output,
            global_top_keywords=global_keywords
        )
