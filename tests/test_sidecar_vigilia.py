"""
El motor no sobrevive a la aplicación
=====================================

La aplicación lanza el motor y lo detiene al cerrarse con normalidad. Pero
si muere de golpe (se cuelga, se mata desde el Administrador de tareas, un
`taskkill /F`), `Drop` no llega a ejecutarse y el motor quedaba huérfano con
el puerto 8765 y un token que nadie conoce: el siguiente arranque encontraba
«otro proceso» en el puerto y el motor se quedaba «cargando» para siempre.

Con `--exit-with-parent`, el motor vigila su entrada estándar, que es una
tubería de la aplicación. Cuando la aplicación muere, sea como sea, el
sistema cierra esa tubería y el motor termina. Sin la opción (arranque a
mano para desarrollo), cerrar la entrada no lo detiene.
"""

import os
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from core.orchestration import sidecar_server

RAIZ = Path(__file__).resolve().parents[1]


class TestVigilarPadre(unittest.TestCase):
    def test_al_cerrarse_la_tuberia_sale_con_cero(self):
        lectura, escritura = os.pipe()
        salidas: list[int] = []
        hecho = threading.Event()

        def salir(codigo: int) -> None:
            salidas.append(codigo)
            hecho.set()

        with open(lectura, "rb", buffering=0) as entrada:
            sidecar_server.vigilar_padre(entrada, salir)
            time.sleep(0.2)
            self.assertEqual(salidas, [], "con la aplicación viva no sale")
            os.close(escritura)
            self.assertTrue(hecho.wait(5), "cerrada la tubería, sale")
        self.assertEqual(salidas, [0])

    def test_sin_entrada_estandar_la_aplicacion_ya_no_esta(self):
        salidas: list[int] = []
        sidecar_server.vigilar_padre(None, salidas.append).join(5)
        self.assertEqual(salidas, [0])


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def espera_puerto(puerto: int, limite: float = 60,
                  proceso: subprocess.Popen[bytes] | None = None) -> bool:
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        if proceso is not None and proceso.poll() is not None:
            return False
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", puerto)) == 0:
                return True
        time.sleep(0.2)
    return False


class TestProcesoReal(unittest.TestCase):
    def lanzar(self, *extra: str) -> tuple[subprocess.Popen[bytes], int]:
        puerto = puerto_libre()
        proceso = subprocess.Popen(
            [sys.executable, "-m", "core.orchestration.sidecar_server", "--insecure-dev",
             "--port", str(puerto), *extra],
            cwd=RAIZ, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.addCleanup(self.terminar, proceso)
        self.assertTrue(espera_puerto(puerto, proceso=proceso), "el motor no llegó a escuchar")
        return proceso, puerto

    @staticmethod
    def terminar(proceso: subprocess.Popen[bytes]) -> None:
        if proceso.poll() is None:
            proceso.kill()
            proceso.wait(timeout=10)

    def test_con_exit_with_parent_termina_al_morir_la_aplicacion(self):
        proceso, _ = self.lanzar("--exit-with-parent")
        entrada = proceso.stdin
        assert entrada is not None
        entrada.close()
        self.assertEqual(proceso.wait(timeout=15), 0)

    def test_sin_la_opcion_cerrar_la_entrada_no_lo_detiene(self):
        proceso, puerto = self.lanzar()
        entrada = proceso.stdin
        assert entrada is not None
        entrada.close()
        time.sleep(1.5)
        self.assertIsNone(proceso.poll())
        self.assertTrue(espera_puerto(puerto, 2))


if __name__ == "__main__":
    unittest.main()
