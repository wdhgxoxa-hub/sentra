"""
La red de tests/_asyncio_lento.py (2026-10-12)
==============================================

asyncio en modo depuración solo apuntaba «Executing <Task …> took 0.117
seconds» y la prueba pasaba. Con la red, un paso que bloquea el bucle más de
`slow_callback_duration` hace fallar la prueba; uno que cede el bucle, no.
"""

import asyncio
import time
import unittest

from tests._asyncio_lento import BucleBloqueado, vigilar


def gastar_cpu(segundos: float) -> None:
    """Trabajo de CPU sin ceder (como un bucle de la app sobre muchas piezas)."""
    fin = time.perf_counter() + segundos
    while time.perf_counter() < fin:
        pass


class TestRedDelBucleBloqueado(unittest.TestCase):

    def setUp(self):
        vigilar()  # ya instalada por tests/__init__.py; se asegura si se corre suelta

    @staticmethod
    def correr(corrutina):
        with asyncio.Runner(debug=True) as runner:
            runner.get_loop().slow_callback_duration = 0.05
            return runner.run(corrutina)

    def test_un_paso_que_bloquea_el_bucle_hace_fallar(self):
        async def bloquea():
            gastar_cpu(0.08)  # trabajo síncrono dentro de la corrutina, sin ceder

        with self.assertRaisesRegex(BucleBloqueado, r"Executing .* took \d+\.\d+ seconds"):
            self.correr(bloquea())

    def test_una_espera_llevada_a_un_hilo_no_falla(self):
        async def cede():
            # Espera fuera del bucle (E/S síncrona en un hilo, que suelta el GIL).
            await asyncio.to_thread(time.sleep, 0.08)
            return "bien"

        self.assertEqual(self.correr(cede()), "bien")


if __name__ == "__main__":
    unittest.main()
