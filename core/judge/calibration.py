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


def _tabla_de_contingencia(verdad: Sequence[Any], prediccion: Sequence[Any]) -> Any:
    import numpy as np

    if len(verdad) != len(prediccion):
        raise ValueError("las dos particiones deben tener los mismos ítems")
    clases = {c: i for i, c in enumerate(dict.fromkeys(verdad))}
    grupos = {g: i for i, g in enumerate(dict.fromkeys(prediccion))}
    tabla = np.zeros((len(clases), len(grupos)), dtype=np.int64)
    for c, g in zip(verdad, prediccion, strict=True):
        tabla[clases[c], grupos[g]] += 1
    return tabla


def adjusted_rand_index(verdad: Sequence[Any], prediccion: Sequence[Any]) -> float:
    """Adjusted Rand Index (Hubert y Arabie, 1985): 1 = igual; ~0 = azar."""
    tabla = _tabla_de_contingencia(verdad, prediccion)

    def pares(x: Any) -> float:
        return float((x * (x - 1) // 2).sum())

    n = int(tabla.sum())
    indice = pares(tabla)
    filas, columnas = pares(tabla.sum(axis=1)), pares(tabla.sum(axis=0))
    esperado = filas * columnas / (n * (n - 1) / 2) if n > 1 else 0.0
    maximo = (filas + columnas) / 2
    if maximo == esperado:
        return 1.0
    return (indice - esperado) / (maximo - esperado)


def purity(verdad: Sequence[Any], prediccion: Sequence[Any]) -> float:
    """Fracción de ítems que caen en la clase mayoritaria de su grupo."""
    tabla = _tabla_de_contingencia(verdad, prediccion)
    return float(tabla.max(axis=0).sum() / tabla.sum()) if tabla.size else 0.0
