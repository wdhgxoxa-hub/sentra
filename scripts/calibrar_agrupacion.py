"""Barrido de umbrales de la agrupación sobre el conjunto dorado (B3).

    python scripts/calibrar_agrupacion.py

Lee tests/fixtures/golden_clusters_e5.npz (vectores e5 ya calculados) y
compara el líder voraz con el enlace promedio. La partición evaluada es la
que ve el juez: los grupos de menos de MIN_CLUSTER_SIZE cuentan como ítems
sueltos. Criterio, fijado antes de mirar resultados: ARI máximo; a igualdad,
más pureza; a igualdad, el umbral más alto. Imprime la tabla en Markdown.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.judge.calibration import adjusted_rand_index, purity
from core.judge.clustering import (
    MIN_CLUSTER_SIZE,
    average_linkage_partition,
    leader_partition,
)

METODOS = {"lider": leader_partition, "enlace_promedio": average_linkage_partition}
UMBRALES = [round(0.78 + 0.01 * i, 2) for i in range(17)]


def efectiva(etiquetas: list[int]) -> list[str]:
    """Los grupos por debajo del tamaño mínimo pasan a ser ítems sueltos."""
    tamanos = Counter(etiquetas)
    return [f"g{e}" if tamanos[e] >= MIN_CLUSTER_SIZE else f"suelto{i}"
            for i, e in enumerate(etiquetas)]


@dataclass(frozen=True)
class Fila:
    metodo: str
    umbral: float
    grupos: int
    pureza: float
    ari: float


def barrido() -> list[Fila]:
    datos = np.load(RAIZ / "tests" / "fixtures" / "golden_clusters_e5.npz")
    dorado = {i["id"]: i for i in json.loads(
        (RAIZ / "tests" / "fixtures" / "golden_clusters.json").read_text(encoding="utf-8"))["items"]}
    ids = [str(i) for i in datos["ids"]]
    verdad = [dorado[i]["group"] for i in ids]
    vectores = [list(v) for v in datos["vectors"]]
    filas = []
    for nombre, metodo in METODOS.items():
        for umbral in UMBRALES:
            pred = efectiva(metodo(vectores, umbral))
            grupos = len({p for p in pred if p.startswith("g")})
            filas.append(Fila(nombre, umbral, grupos, purity(verdad, pred),
                              adjusted_rand_index(verdad, pred)))
    return filas


def elegir(filas: list[Fila]) -> Fila:
    return max(filas, key=lambda f: (round(f.ari, 6), round(f.pureza, 6), f.umbral))


if __name__ == "__main__":
    filas = barrido()
    print("| método | umbral | grupos (>= 3) | pureza | ARI |")
    print("|---|---|---|---|---|")
    for f in filas:
        print(f"| {f.metodo} | {f.umbral:.2f} | {f.grupos} | {f.pureza:.3f} | {f.ari:.3f} |")
    mejor = elegir(filas)
    print(f"\nElegido: {mejor.metodo} con umbral {mejor.umbral:.2f} "
          f"(pureza {mejor.pureza:.3f}, ARI {mejor.ari:.3f})")
