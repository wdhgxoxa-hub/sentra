"""
Identidad estable de cada oportunidad (AUD-019, decisión D-G)
=============================================================

`cluster_key` se calcula con la intención y las palabras clave: en cuanto un
problema ganaba una palabra entre escaneos, cambiaba de clave y perdía su
historial y su validación. Ahora cada oportunidad tiene un UUID que hereda
la lectura nueva si comparte al menos MEMBER_JACCARD_MIN de sus señales o,
si no, KEYWORD_JACCARD_MIN de sus palabras clave. Si no, UUID nuevo. Dos
problemas nunca heredan el mismo UUID.
"""

import unittest
from pathlib import Path

from core.storage.identity import (
    KEYWORD_JACCARD_MIN,
    MEMBER_JACCARD_MIN,
    Candidato,
    Previo,
    asignar_identidades,
    jaccard,
)

RAIZ = Path(__file__).resolve().parents[1]


class TestAsignacion(unittest.TestCase):

    def test_los_umbrales_son_constantes_con_nombre(self):
        self.assertEqual(MEMBER_JACCARD_MIN, 0.5)
        self.assertEqual(KEYWORD_JACCARD_MIN, 0.6)

    def test_jaccard(self):
        self.assertEqual(jaccard({"a", "b"}, {"b", "c"}), 1 / 3)
        self.assertEqual(jaccard(set(), set()), 0.0)

    def test_un_problema_que_gana_palabras_conserva_su_uuid_por_sus_senales(self):
        previos = [Previo("uuid-a", {"p1", "p2", "p3"}, {"invoice", "manual"})]
        nuevos = [Candidato("complaint:export|invoice|manual", {"p1", "p2", "p3", "p4"},
                            {"invoice", "manual", "export", "reconcile", "csv"})]
        self.assertEqual(asignar_identidades(nuevos, previos),
                         {"complaint:export|invoice|manual": "uuid-a"})

    def test_sin_senales_comunes_hereda_por_palabras_clave(self):
        previos = [Previo("uuid-a", {"p1"}, {"invoice", "manual", "export"})]
        nuevos = [Candidato("k", {"p9"}, {"invoice", "manual", "export", "csv"})]
        self.assertEqual(asignar_identidades(nuevos, previos), {"k": "uuid-a"})

    def test_por_debajo_de_los_dos_umbrales_es_una_oportunidad_nueva(self):
        previos = [Previo("uuid-a", {"p1", "p2", "p3"}, {"invoice", "manual"})]
        nuevos = [Candidato("k", {"p3", "p8", "p9"}, {"invoice", "onboarding", "sso"})]
        self.assertEqual(asignar_identidades(nuevos, previos), {"k": None})

    def test_dos_problemas_distintos_no_heredan_el_mismo_uuid(self):
        previos = [Previo("uuid-a", {"p1", "p2"}, {"invoice", "manual"})]
        nuevos = [
            Candidato("uno", {"p1", "p2"}, {"invoice", "manual"}),
            Candidato("otro", {"p1", "p2", "p5"}, {"invoice", "manual"}),
        ]
        asignacion = asignar_identidades(nuevos, previos)
        self.assertEqual(asignacion["uno"], "uuid-a")  # el mejor emparejado
        self.assertIsNone(asignacion["otro"])

    def test_las_senales_mandan_sobre_las_palabras(self):
        previos = [
            Previo("por-palabras", {"x1"}, {"invoice", "manual"}),
            Previo("por-senales", {"p1", "p2"}, {"billing"}),
        ]
        nuevos = [Candidato("k", {"p1", "p2"}, {"invoice", "manual"})]
        self.assertEqual(asignar_identidades(nuevos, previos), {"k": "por-senales"})


TEST_DB = "rir_identity_test"


if __name__ == "__main__":
    unittest.main()
