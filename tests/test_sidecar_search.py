"""
/api/search sobre la evidencia multifuente (D-C4)
=================================================

La ruta delega en `_buscar` (e5 + PostgreSQL), que aquí es un doble: ningún
test abre el modelo ni la base real. Sin almacén de vectores (el sidecar sin
persistencia) la búsqueda dice que no está disponible, con código.
"""

import unittest
from unittest import mock

from core.sources.attribution import attribution_fields
from tests.test_sidecar_config import ConfigTestCase

HITS = [{"id": "stackexchange:1", "source": "stackexchange", "community": "Stack Overflow",
         "kind": "question", "title": None, "excerpt": "queja inventada",
         "url": "https://example.com/q/1", "created_at": "2026-09-01T00:00:00+00:00",
         "data_source": "real",
         "attribution": attribution_fields("stackexchange", "Stack Overflow", "https://example.com/q/1"),
         "rrf_score": 0.03, "dense_rank": 2, "lexical_rank": None}]


class TestBusquedaDeEvidencia(ConfigTestCase):
    def test_sin_almacen_de_vectores_no_esta_disponible(self):
        respuesta = self.client.post("/api/search", json={"query": "correo"})
        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(respuesta.json()["detail"]["code"], "search_unavailable")

    def test_devuelve_los_resultados_en_camel_case(self):
        from core.orchestration.sidecar import search

        with mock.patch.object(search, "_disponible", return_value=True), \
                mock.patch.object(search, "_buscar", return_value=HITS) as buscar:
            cuerpo = self.client.post("/api/search", json={"query": "correo", "limit": 7}).json()
        self.assertEqual(buscar.call_args.args[1:], ("correo", 7))
        self.assertEqual(cuerpo["query"], "correo")
        hit = cuerpo["hits"][0]
        self.assertEqual((hit["denseRank"], hit["lexicalRank"], hit["dataSource"]), (2, None, "real"))
        self.assertEqual(hit["attribution"]["badge"], "Stack Exchange")

    def test_consulta_vacia_o_limite_desmedido_se_rechazan(self):
        self.assertEqual(self.client.post("/api/search", json={"query": "  "}).status_code, 422)
        self.assertEqual(self.client.post("/api/search", json={"query": "x", "limit": 500}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
