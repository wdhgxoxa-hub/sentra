"""
Identidad estable de cada oportunidad (AUD-019, decisión D-G)
=============================================================

`cluster_key` describe una lectura (intención + palabras clave) y cambia en
cuanto el problema gana o pierde una palabra entre escaneos. Por eso no
sirve para enlazar el historial ni la validación humana: cada oportunidad
tiene un UUID (`opportunity_id`) que la lectura nueva hereda de una
anterior si

1. comparte al menos MEMBER_JACCARD_MIN de sus señales (las mismas quejas
   siguen ahí: es el mismo problema aunque se describa distinto), o, si no,
2. comparte al menos KEYWORD_JACCARD_MIN de sus palabras clave.

Si ninguna anterior llega a esos umbrales, es una oportunidad nueva. El
emparejamiento es uno a uno y va de mejor a peor: dos lecturas del mismo
escaneo nunca heredan el mismo UUID, ni una lectura hereda dos.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

#: Fracción de señales compartidas para considerar que es el mismo problema.
MEMBER_JACCARD_MIN = 0.5

#: Fracción de palabras clave compartidas, cuando las señales no bastan.
KEYWORD_JACCARD_MIN = 0.6


@dataclass(frozen=True)
class Candidato:
    """Una lectura del escaneo en curso."""

    clave: str
    miembros: set[str]
    palabras: set[str]


@dataclass(frozen=True)
class Previo:
    """La última lectura conocida de una oportunidad ya persistida."""

    opportunity_id: str
    miembros: set[str]
    palabras: set[str]


def jaccard(a: set[str], b: set[str]) -> float:
    """|A ∩ B| / |A ∪ B|; 0 si los dos están vacíos."""
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def asignar_identidades(
    nuevos: Sequence[Candidato], previos: Sequence[Previo]
) -> dict[str, str | None]:
    """UUID heredado por cada lectura nueva, o None si es una oportunidad nueva."""
    # (nivel, -parecido, índice): primero las coincidencias por señales,
    # luego por palabras; dentro de cada nivel, las más parecidas.
    parejas: list[tuple[int, float, int, int]] = []
    for i, nuevo in enumerate(nuevos):
        for j, previo in enumerate(previos):
            por_senales = jaccard(nuevo.miembros, previo.miembros)
            if por_senales >= MEMBER_JACCARD_MIN:
                parejas.append((0, -por_senales, i, j))
                continue
            por_palabras = jaccard(nuevo.palabras, previo.palabras)
            if por_palabras >= KEYWORD_JACCARD_MIN:
                parejas.append((1, -por_palabras, i, j))

    asignacion: dict[str, str | None] = {nuevo.clave: None for nuevo in nuevos}
    nuevos_usados: set[int] = set()
    previos_usados: set[int] = set()
    for _nivel, _parecido, i, j in sorted(parejas):
        if i in nuevos_usados or j in previos_usados:
            continue
        asignacion[nuevos[i].clave] = previos[j].opportunity_id
        nuevos_usados.add(i)
        previos_usados.add(j)
    return asignacion
