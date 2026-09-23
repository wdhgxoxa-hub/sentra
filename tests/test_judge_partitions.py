"""
Métodos de partición de la agrupación (B3)
==========================================

Los dos candidatos del barrido, como funciones puras sobre vectores:
- líder voraz (clustering-v1): cada vector al grupo cuyo centroide supera
  el umbral;
- enlace promedio (jerárquico aglomerativo): se unen los dos grupos con
  mayor similitud media mientras supere el umbral.
Vectores hechos a mano; deterministas.
"""

import unittest

from core.judge.clustering import average_linkage_partition, leader_partition

TRES_GRUPOS = [
    [1.0, 0.0, 0.0], [0.97, 0.05, 0.0], [0.96, 0.0, 0.08],
    [0.0, 1.0, 0.0], [0.04, 0.98, 0.0], [0.0, 0.95, 0.07],
    [0.0, 0.0, 1.0], [0.06, 0.0, 0.97],
]
ESPERADO = [0, 0, 0, 1, 1, 1, 2, 2]


def mismas_particiones(a, b):
    return {tuple(i for i, x in enumerate(a) if x == g) for g in set(a)} == \
        {tuple(i for i, x in enumerate(b) if x == g) for g in set(b)}


class TestParticiones(unittest.TestCase):
    def test_los_dos_metodos_recuperan_grupos_claros(self):
        for metodo in (leader_partition, average_linkage_partition):
            with self.subTest(metodo=metodo.__name__):
                self.assertTrue(mismas_particiones(metodo(TRES_GRUPOS, 0.9), ESPERADO))

    def test_umbral_por_encima_de_todo_deja_cada_uno_solo(self):
        for metodo in (leader_partition, average_linkage_partition):
            with self.subTest(metodo=metodo.__name__):
                self.assertEqual(len(set(metodo(TRES_GRUPOS, 0.9999))), len(TRES_GRUPOS))

    def test_umbral_por_debajo_de_todo_une_todo(self):
        for metodo in (leader_partition, average_linkage_partition):
            with self.subTest(metodo=metodo.__name__):
                self.assertEqual(len(set(metodo(TRES_GRUPOS, -1.0))), 1)

    def test_enlace_promedio_no_encadena_como_el_minimo(self):
        # a~b y b~c, pero a y c lejos: el promedio de {a,b} con c no llega.
        cadena = [[1.0, 0.0], [0.8, 0.6], [0.28, 0.96]]
        self.assertEqual(len(set(average_linkage_partition(cadena, 0.79))), 2)

    def test_son_deterministas(self):
        self.assertEqual(average_linkage_partition(TRES_GRUPOS, 0.9),
                         average_linkage_partition(TRES_GRUPOS, 0.9))


if __name__ == "__main__":
    unittest.main()
