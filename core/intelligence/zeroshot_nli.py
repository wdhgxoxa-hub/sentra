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

Regla de decisión (AUD-005)
---------------------------
Sin evidencia, la respuesta es `UNDETERMINED_LABEL`, nunca la primera etiqueta
de la lista. Antes, con similitudes empatadas, `np.argmax` devolvía el índice
0, que en las tres taxonomías es la etiqueta más extrema ("ready to buy",
"severe blocker", "negative frustration"): el corpus de demostración salía
entero como «bloqueante grave». Ahora un empate, una similitud máxima baja o
un margen corto entre las dos primeras dan "undetermined", así que el orden
de la lista no puede influir en el resultado.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

#: Etiqueta de «no hay evidencia suficiente para decidir». Aporta cero a su
#: componente de la puntuación (ver engine.py y aggregation.py).
UNDETERMINED_LABEL = "undetermined"

# --- Umbrales de decisión: el único sitio donde se fijan -------------------
#
# Motor heurístico (similitud coseno TF-IDF entre texto e hipótesis).
# Calibrados midiendo el corpus de demostración y textos con la etiqueta
# explícita (2026-09-23):
#   - sin evidencia: similitud idéntica en TODAS las etiquetas (empate: 0.000
#     o, si el texto comparte una palabra de la plantilla, 0.030 en todas);
#   - con evidencia: similitud máxima entre 0.068 ("Need alternative to
#     Salesforce" -> "seeking alternative") y 0.656, con margen = similitud;
#   - único falso positivo: 0.044 con margen 0.025, arrastrado por la palabra
#     "problem" de la propia plantilla ("This tool fixed my broken invoice problem").
# 0.05 queda dentro de los dos huecos: por encima de 0.044 / 0.025 y por
# debajo de 0.068.
HEURISTIC_MIN_SIMILARITY = 0.05
HEURISTIC_MIN_MARGIN = 0.05

# Motor transformers (probabilidades). Sin el modelo instalado no hay datos
# para calibrarlos, así que solo se exige lo mínimo: que no haya empate.
TRANSFORMERS_MIN_SCORE = 0.0
TRANSFORMERS_MIN_MARGIN = 0.0

Engine = Literal["heuristic", "transformers"]

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
    all_scores: dict[str, float] = Field(default_factory=dict)
    candidate_labels: list[str] = Field(default_factory=list)
    hypothesis_template: str = ""
    #: Motor que produjo realmente esta etiqueta.
    engine: Engine = "heuristic"


def decide(
    scores: Mapping[str, float], min_top: float, min_margin: float
) -> str:
    """
    Elige etiqueta a partir de sus puntuaciones, o `UNDETERMINED_LABEL`.

    Es indeterminado si la mejor no alcanza `min_top`, si le saca a la segunda
    menos de `min_margin`, o si empatan: un empate no se resuelve por el orden
    de la lista, porque ese orden no es evidencia.
    """
    if not scores:
        return UNDETERMINED_LABEL
    ordenadas = sorted(scores.values(), reverse=True)
    mejor = ordenadas[0]
    segunda = ordenadas[1] if len(ordenadas) > 1 else 0.0
    margen = mejor - segunda
    if mejor < min_top or margen < min_margin or margen <= 0.0:
        return UNDETERMINED_LABEL
    return next(label for label, score in scores.items() if score == mejor)


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
        self.hf_pipeline: Callable[..., Any] | None = None

        if use_transformers_if_available:
            try:
                from transformers import pipeline
                self.hf_pipeline = pipeline("zero-shot-classification", model=model_name)
                logger.info(f"Modelo HuggingFace {model_name} cargado con éxito para Zero-Shot NLI.")
            # Frontera con una dependencia opcional: sin transformers, sin
            # modelo descargado o sin memoria, se queda el motor heurístico.
            except Exception:  # noqa: BLE001 - dependencia opcional (transformers)
                logger.info("Motor Transformers no disponible o sin soporte GPU. Usando motor local Semantic TF-IDF.")

    def _softmax(self, scores: np.ndarray) -> np.ndarray:
        """Función softmax numéricamente estable."""
        exp_scores = np.exp(scores - np.max(scores))
        return np.asarray(exp_scores / exp_scores.sum())

    def _local_semantic_classify(
        self,
        text: str,
        candidate_labels: Sequence[str],
        hypothesis_template: str
    ) -> ZeroShotResult:
        """
        Inferencia semántica local determinista basada en proyección vectorial TF-IDF (scikit-learn).

        La decisión se toma sobre la similitud coseno (con `decide`); el
        softmax solo sirve para informar de una confianza relativa.
        """
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        hypotheses = [hypothesis_template.format(label) for label in candidate_labels]
        corpus = [text, *hypotheses]

        # Vectorización combinada de palabras y bigramas
        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            stop_words="english",
            sublinear_tf=True
        )

        try:
            tfidf_matrix = vectorizer.fit_transform(corpus)
        except ValueError as e:
            # Vocabulario vacío (solo palabras vacías): no hay evidencia.
            logger.warning(f"Texto sin vocabulario evaluable: {e}")
            return ZeroShotResult(
                predicted_label=UNDETERMINED_LABEL,
                confidence=0.0,
                all_scores={},
                candidate_labels=list(candidate_labels),
                hypothesis_template=hypothesis_template,
                engine="heuristic",
            )

        similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]
        # Multiplicar por un factor de temperatura para acentuar contrastes
        probs = self._softmax(similarities * 3.5)

        label = decide(
            {lab: float(similarities[i]) for i, lab in enumerate(candidate_labels)},
            HEURISTIC_MIN_SIMILARITY,
            HEURISTIC_MIN_MARGIN,
        )
        confidence = (
            0.0 if label == UNDETERMINED_LABEL
            else round(float(probs[list(candidate_labels).index(label)]), 4)
        )

        return ZeroShotResult(
            predicted_label=label,
            confidence=confidence,
            all_scores={lab: round(float(probs[i]), 4) for i, lab in enumerate(candidate_labels)},
            candidate_labels=list(candidate_labels),
            hypothesis_template=hypothesis_template,
            engine="heuristic",
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
            # Frontera con el modelo: si la inferencia falla, clasifica el
            # motor heurístico y el resultado lo declara en `engine`.
            except Exception as e:  # noqa: BLE001 - frontera con el modelo
                logger.warning(f"Fallo en inferencia HuggingFace: {e}. Alternando a motor local.")
            else:
                scores_dict = {
                    label: round(float(score), 4)
                    for label, score in zip(res["labels"], res["scores"], strict=True)
                }
                label = decide(scores_dict, TRANSFORMERS_MIN_SCORE, TRANSFORMERS_MIN_MARGIN)
                return ZeroShotResult(
                    predicted_label=label,
                    confidence=0.0 if label == UNDETERMINED_LABEL else scores_dict[label],
                    all_scores=scores_dict,
                    candidate_labels=list(candidate_labels),
                    hypothesis_template=hypothesis_template,
                    engine="transformers",
                )

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
