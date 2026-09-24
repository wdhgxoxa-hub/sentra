"""
Calibración de la agrupación con métrica (B3, clustering-v2)
============================================================

Sobre el conjunto dorado de agrupación (6 subproblemas de «notificaciones»,
es/en, más ruido) y sus vectores e5 guardados (tests/fixtures/
golden_clusters_e5.npz, generados con scripts/embed_golden_clusters.py):
la agrupación del juez no puede bajar de la pureza y el ARI logrados al
elegir clustering-v2 (barrido en scripts/calibrar_agrupacion.py).
"""

import json
import unittest
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from core.evidence.model import EvidenceItem
from core.judge.calibration import adjusted_rand_index, purity
from core.judge.clustering import (
    CLUSTER_MIN_SIMILARITY,
    CLUSTERING_METHOD,
    CLUSTERING_VERSION,
    MIN_CLUSTER_SIZE,
    average_linkage_partition,
    cluster_evidence,
)
from core.storage.embeddings import E5_POOLING, MULTILINGUAL_MODEL_NAME

FIXTURES = Path(__file__).parent / "fixtures"
#: Logrado al elegir clustering-v2 (enlace promedio, 0,82).
PURITY_ACHIEVED = 0.735
ARI_ACHIEVED = 0.487


def cargar():
    datos = np.load(FIXTURES / "golden_clusters_e5.npz")
    dorado = json.loads((FIXTURES / "golden_clusters.json").read_text(encoding="utf-8"))
    return datos, dorado


class TestCalibracion(unittest.TestCase):
    def test_los_vectores_guardados_son_del_modelo_y_pooling_actuales(self):
        datos, dorado = cargar()
        self.assertEqual(str(datos["model"]), MULTILINGUAL_MODEL_NAME)
        self.assertEqual(str(datos["pooling"]), E5_POOLING)
        self.assertEqual(str(datos["golden_version"]), dorado["version"])
        self.assertEqual([str(i) for i in datos["ids"]], [i["id"] for i in dorado["items"]])

    def test_clustering_v2_elegido_por_la_metrica(self):
        # v3 (AUD2-001) cambia qué entra (solo dolor pertinente) y v4 (AUD2-006) cómo
        # se nombran los grupos; ninguna el método ni el umbral.
        self.assertEqual((CLUSTERING_VERSION, CLUSTERING_METHOD, CLUSTER_MIN_SIMILARITY),
                         ("clustering-v5", "average_linkage", 0.82))

    def test_agrupar_por_la_frase_del_problema_supera_al_post_entero(self):
        # clustering-v5, medido antes de fijarlo (scripts/embed_golden_clusters.py):
        # con el contexto común del tema alrededor de cada frase, agrupar por el post
        # entero cae a ARI 0,005 en 0,82 (mejor umbral: 0,025); por la frase, 0,487.
        dorado = json.loads((FIXTURES / "golden_clusters.json").read_text(encoding="utf-8"))
        grupo_de = {str(i["id"]): i["group"] for i in dorado["items"]}

        def ari(fichero):
            datos = np.load(FIXTURES / fichero)
            verdad = [grupo_de[str(i)] for i in datos["ids"]]
            etiquetas = average_linkage_partition(list(datos["vectors"]), CLUSTER_MIN_SIMILARITY)
            tamanos = Counter(etiquetas)
            efectiva = [f"g{e}" if tamanos[e] >= MIN_CLUSTER_SIZE else f"s{n}"
                        for n, e in enumerate(etiquetas)]
            return adjusted_rand_index(verdad, efectiva)

        self.assertGreaterEqual(ari("golden_clusters_e5.npz"), ARI_ACHIEVED)
        self.assertLess(ari("golden_clusters_posts_e5.npz"), 0.1)

    def test_la_agrupacion_del_juez_no_baja_de_lo_logrado(self):
        datos, dorado = cargar()
        grupo_de = {i["id"]: i["group"] for i in dorado["items"]}
        ahora = datetime(2026, 9, 1, tzinfo=UTC)
        items, vectores = [], {}
        for n, (id_, vector) in enumerate(zip(datos["ids"], datos["vectors"], strict=True)):
            item_id = f"hackernews:{id_}"
            items.append(EvidenceItem(id=item_id, source="hackernews", community="c", kind="post",
                                      text=f"texto {id_}", url="https://example.com/x",
                                      author_hash=None, created_at=ahora - timedelta(minutes=n),
                                      fetched_at=ahora, data_source="real"))
            vectores[item_id] = [float(x) for x in vector]
        grupos = cluster_evidence(items, vectores)
        asignado = {m: g.key for g in grupos for m in g.member_ids}
        self.assertTrue(all(len(g.member_ids) >= MIN_CLUSTER_SIZE for g in grupos))
        verdad = [grupo_de[i.id.split(":", 1)[1]] for i in items]
        pred = [asignado.get(i.id, f"suelto-{i.id}") for i in items]
        self.assertGreaterEqual(round(purity(verdad, pred), 3), PURITY_ACHIEVED)
        self.assertGreaterEqual(round(adjusted_rand_index(verdad, pred), 3), ARI_ACHIEVED)
        self.assertEqual(len(grupos), 6, Counter(pred))


if __name__ == "__main__":
    unittest.main()
