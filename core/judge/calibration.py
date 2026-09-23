"""
Calibración del etiquetado contra el conjunto dorado (F3.7)
===========================================================

La misma medida sirve para los dobles y para el modelo real: por campo,
la fracción de ítems en que la etiqueta verificada coincide con la
esperada. Un `undetermined` cuenta como desacuerdo (no se premia callar), y
aparte se informa de la cobertura (ítems con etiqueta del LLM).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .labels import VerifiedLabel

FIELDS = ("is_pain", "intent", "workaround_described", "wtp_signal")


@dataclass(frozen=True)
class Agreement:
    items: int
    per_field: dict[str, float]
    #: Ítems con etiqueta del LLM (sin motivo de undetermined).
    coverage: float


def _esperado(campo: str, valor: Any) -> str:
    if campo == "intent":
        return str(valor)
    return "yes" if valor else "no"


def agreement(golden: Sequence[Mapping[str, Any]], labels: Mapping[str, VerifiedLabel]) -> Agreement:
    """Concordancia de `labels` (por id dorado) con las etiquetas esperadas."""
    medidos = [d for d in golden if d["id"] in labels]
    if not medidos:
        return Agreement(0, dict.fromkeys(FIELDS, 0.0), 0.0)
    por_campo = {}
    for campo in FIELDS:
        aciertos = sum(getattr(labels[d["id"]], campo) == _esperado(campo, d["expected"][campo])
                       for d in medidos)
        por_campo[campo] = aciertos / len(medidos)
    cubiertos = sum(labels[d["id"]].undetermined_reason is None for d in medidos)
    return Agreement(len(medidos), por_campo, cubiertos / len(medidos))
