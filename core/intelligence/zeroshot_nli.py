"""
Clasificador Zero-Shot Local Basado en Inferencia de Lenguaje Natural (NLI)
===========================================================================
Extraído y adaptado de reddit-sentiment-zero-shot (1_step.ipynb).

Proporciona:
1. Clasificación Zero-Shot sin necesidad de datasets etiquetados previos ni coste de API.
2. Inferencia de polaridad, intención de compra y severidad de dolor mediante premisa-hipótesis.
3. Arquitectura dual de inferencia:
   - Modo Primario (Transformers): Utiliza pipeline('zero-shot-classification') si PyTorch/Transformers está disponible.
   - Modo Local Autónomo (Semantic TF-IDF Cosine & Softmax): Motor ultrarrápido y ligero basado en scikit-learn
     que evalúa la probabilidad de correspondencia semántica entre el texto premisa y las hipótesis generadas.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Union
import numpy as np
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Taxonomías de etiquetas predefinidas para el radar
INTENT_CANDIDATE_LABELS = [
    "ready to buy",
    "seeking recommendation",
    "seeking alternative",
    "comparing products",
    "casual discussion"
]

PAIN_CANDIDATE_LABELS = [
    "severe blocker",
    "time consuming friction",
    "minor inconvenience",
    "no problem"
]

SENTIMENT_CANDIDATE_LABELS = [
    "negative frustration",
    "neutral inquiry",
    "positive praise"
]


class ZeroShotResult(BaseModel):
    """Resultado estructurado de la clasificación Zero-Shot NLI."""
    predicted_label: str
    confidence: float
    all_scores: Dict[str, float] = Field(default_factory=dict)
    candidate_labels: List[str] = Field(default_factory=list)
    hypothesis_template: str = ""


class ZeroShotNLIClassifier:
    """
    Clasificador local Zero-Shot que infiere categorías e intenciones sin requerir fine-tuning.
    """

    def __init__(
        self,
        model_name: str = "facebook/bart-large-mnli",
        use_transformers_if_available: bool = True
    ) -> None:
        self.model_name = model_name
        self.hf_pipeline = None

        if use_transformers_if_available:
            try:
                from transformers import pipeline
                self.hf_pipeline = pipeline("zero-shot-classification", model=model_name)
                logger.info(f"Modelo HuggingFace {model_name} cargado con éxito para Zero-Shot NLI.")
            except Exception:
                logger.info("Motor Transformers no disponible o sin soporte GPU. Usando motor local Semantic TF-IDF.")

    def _softmax(self, scores: np.ndarray) -> np.ndarray:
        """Función softmax numéricamente estable."""
        exp_scores = np.exp(scores - np.max(scores))
        return exp_scores / exp_scores.sum()

    def _local_semantic_classify(
        self,
        text: str,
        candidate_labels: Sequence[str],
        hypothesis_template: str
    ) -> ZeroShotResult:
        """
        Inferencia semántica local determinista basada en proyección vectorial TF-IDF (scikit-learn).
        Genera hipótesis dinámicas (ej: 'This discussion indicates ready to buy') y calcula
        la similitud coseno frente a la premisa textual, aplicando softmax para normalizar a probabilidades.
        """
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        hypotheses = [hypothesis_template.format(label) for label in candidate_labels]
        corpus = [text] + hypotheses

        # Vectorización combinada de palabras y bigramas
        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            stop_words="english",
            sublinear_tf=True
        )

        try:
            tfidf_matrix = vectorizer.fit_transform(corpus)
            text_vec = tfidf_matrix[0:1]
            hyp_vecs = tfidf_matrix[1:]

            similarities = cosine_similarity(text_vec, hyp_vecs)[0]
            # Multiplicar por un factor de temperatura para acentuar contrastes
            probs = self._softmax(similarities * 3.5)

            scores_dict = {
                label: round(float(probs[i]), 4)
                for i, label in enumerate(candidate_labels)
            }

            best_idx = int(np.argmax(probs))
            best_label = candidate_labels[best_idx]
            best_confidence = round(float(probs[best_idx]), 4)

            return ZeroShotResult(
                predicted_label=best_label,
                confidence=best_confidence,
                all_scores=scores_dict,
                candidate_labels=list(candidate_labels),
                hypothesis_template=hypothesis_template
            )
        except Exception as e:
            logger.error(f"Error en clasificación semántica local: {e}")
            # Fallback seguro uniforme
            default_prob = round(1.0 / len(candidate_labels), 4)
            return ZeroShotResult(
                predicted_label=candidate_labels[0],
                confidence=default_prob,
                all_scores={l: default_prob for l in candidate_labels},
                candidate_labels=list(candidate_labels),
                hypothesis_template=hypothesis_template
            )

    def classify(
        self,
        text: str,
        candidate_labels: Sequence[str],
        hypothesis_template: str = "This text is about {}."
    ) -> ZeroShotResult:
        """
        Ejecuta la clasificación Zero-Shot sobre la premisa dada.
        """
        if not text or not candidate_labels:
            raise ValueError("Texto y etiquetas candidatas son requeridos.")

        # Si el pipeline de HuggingFace está activo, usarlo
        if self.hf_pipeline is not None:
            try:
                res = self.hf_pipeline(
                    text,
                    candidate_labels=list(candidate_labels),
                    hypothesis_template=hypothesis_template
                )
                scores_dict = {
                    label: round(float(score), 4)
                    for label, score in zip(res["labels"], res["scores"])
                }
                return ZeroShotResult(
                    predicted_label=res["labels"][0],
                    confidence=round(float(res["scores"][0]), 4),
                    all_scores=scores_dict,
                    candidate_labels=list(candidate_labels),
                    hypothesis_template=hypothesis_template
                )
            except Exception as e:
                logger.warning(f"Fallo en inferencia HuggingFace: {e}. Alternando a motor local.")

        # Motor local determinista
        return self._local_semantic_classify(text, candidate_labels, hypothesis_template)

    def classify_buying_intent(self, text: str) -> ZeroShotResult:
        """Clasifica la intención comercial del usuario."""
        template = "The user in this discussion is {}."
        return self.classify(text, INTENT_CANDIDATE_LABELS, hypothesis_template=template)

    def classify_pain_severity(self, text: str) -> ZeroShotResult:
        """Clasifica el nivel de severidad del dolor o problema reportado."""
        template = "The problem described by the user is a {}."
        return self.classify(text, PAIN_CANDIDATE_LABELS, hypothesis_template=template)

    def classify_sentiment(self, text: str) -> ZeroShotResult:
        """Clasifica la polaridad emocional del comentario."""
        template = "The customer sentiment expressed here is {}."
        return self.classify(text, SENTIMENT_CANDIDATE_LABELS, hypothesis_template=template)
