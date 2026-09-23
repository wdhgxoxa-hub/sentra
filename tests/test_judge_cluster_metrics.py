"""
Métricas de agrupación (B3): pureza y Adjusted Rand Index
=========================================================

Implementadas con numpy (sin dependencias nuevas) y comprobadas contra
valores conocidos: el ejemplo de la documentación de scikit-learn
(adjusted_rand_score([0,0,0,1,1,1], [0,0,1,1,2,2]) = 0,2424…) y casos límite.
"""

import unittest

from core.judge.calibration import adjusted_rand_index, purity


class TestARI(unittest.TestCase):
    def test_particiones_identicas_o_permutadas_dan_1(self):
        self.assertAlmostEqual(adjusted_rand_index([0, 0, 1, 1, 2], [0, 0, 1, 1, 2]), 1.0)
        self.assertAlmostEqual(adjusted_rand_index([0, 0, 1, 1, 2], ["b", "b", "a", "a", "c"]), 1.0)

    def test_ejemplo_de_la_documentacion_de_scikit_learn(self):
        self.assertAlmostEqual(adjusted_rand_index([0, 0, 0, 1, 1, 1], [0, 0, 1, 1, 2, 2]),
                               0.24242424242424246)

    def test_todo_en_un_grupo_frente_a_grupos_reales_da_0(self):
        self.assertAlmostEqual(adjusted_rand_index([0, 0, 1, 1], [0, 0, 0, 0]), 0.0)

    def test_tamanos_distintos_es_un_error(self):
        with self.assertRaises(ValueError):
            adjusted_rand_index([0, 1], [0])


class TestPureza(unittest.TestCase):
    def test_ejemplo(self):
        self.assertAlmostEqual(purity([0, 0, 0, 1, 1, 1], [0, 0, 1, 1, 2, 2]), 5 / 6)

    def test_un_solo_grupo_con_todo_mezclado(self):
        self.assertAlmostEqual(purity([0, 0, 1, 1], [9, 9, 9, 9]), 0.5)

    def test_cada_item_suelto_es_puro(self):
        self.assertAlmostEqual(purity([0, 0, 1, 1], [1, 2, 3, 4]), 1.0)


if __name__ == "__main__":
    unittest.main()
