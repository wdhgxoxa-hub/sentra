"""
La capa Linux de la prueba de humo (tests/humo_linux.py)
========================================================

En Linux el humo abre la app dentro de una pantalla virtual (Xvfb) y la
controla con WebKitWebDriver. Aquí se prueba, sin lanzar nada, lo que decide:
el entorno con el que se abre la app, cómo se cuentan los motores y los
procesos hijos en /proc, cuándo una ventana de tu escritorio es de SENTRA y
el cliente de WebDriver (contra un servidor falso).
"""

import json
import os
import shutil
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, ClassVar


def proceso(proc: Path, pid: int, *, cmdline: list[str], comm: str = "python",
            hijos: tuple[int, ...] = (), estado: str = "S") -> None:
    carpeta = proc / str(pid)
    (carpeta / "task" / str(pid)).mkdir(parents=True)
    (carpeta / "cmdline").write_bytes(b"\0".join(a.encode() for a in cmdline) + b"\0")
    (carpeta / "comm").write_text(comm + "\n")
    (carpeta / "status").write_text(f"Name:\t{comm}\nState:\t{estado} (x)\n")
    (carpeta / "task" / str(pid) / "children").write_text(" ".join(map(str, hijos)) + (" " if hijos else ""))


class TestEntorno(unittest.TestCase):
    def test_la_app_va_a_la_pantalla_virtual_a_la_vista_y_con_su_perfil(self):
        """En Xvfb la ventana se muestra: oculta, WebKitGTK no le da tamaño (0×0) y
        todo parece desbordar. Ahí no roba el foco: es otra pantalla, sin gestor."""
        from unittest import mock

        from tests.humo_linux import entorno

        with mock.patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":0",
                                            "HYPRLAND_INSTANCE_SIGNATURE": "x"}):
            valores = entorno(Path("/tmp/perfil"), ":99")
        self.assertEqual(valores["DISPLAY"], ":99")
        self.assertEqual(valores["GDK_BACKEND"], "x11")
        self.assertNotIn("WAYLAND_DISPLAY", valores)
        self.assertNotIn("HYPRLAND_INSTANCE_SIGNATURE", valores)
        self.assertNotIn("SENTRA_VENTANA_DISCRETA", valores)
        self.assertEqual(valores["SENTRA_PERFIL_WEBVIEW"], "/tmp/perfil")
        self.assertNotIn("TAURI_WEBVIEW_AUTOMATION", valores)

    def test_solo_la_apertura_con_control_remoto_permite_automatizar(self):
        from tests.humo_linux import entorno

        self.assertEqual(entorno(Path("/tmp/p"), ":99", automatizada=True)["TAURI_WEBVIEW_AUTOMATION"], "true")


class TestProcesos(unittest.TestCase):
    def test_cuenta_solo_los_motores_del_puerto_del_humo(self):
        from tests.humo_linux import motores_en

        with TemporaryDirectory() as tmp:
            proc = Path(tmp)
            proceso(proc, 10, cmdline=["/r/.venv/bin/python", "-m", "core.orchestration.sidecar_server", "--port", "8765"])
            proceso(proc, 11, cmdline=["/r/.venv/bin/python", "-m", "core.orchestration.sidecar_server", "--port", "9000"])
            proceso(proc, 12, cmdline=["bash", "-c", "grep orchestration.sidecar_server"])
            proceso(proc, 13, cmdline=["/r/.venv/bin/python", "-m", "core.orchestration.sidecar_server", "--port", "8765"],
                    estado="Z")
            (proc / "self").mkdir()
            self.assertEqual(motores_en(proc), 1)

    def test_los_descendientes_se_leen_de_children(self):
        from tests.humo_linux import descendientes_en

        with TemporaryDirectory() as tmp:
            proc = Path(tmp)
            proceso(proc, 1, cmdline=["WebKitWebDriver"], hijos=(2,))
            proceso(proc, 2, cmdline=["sentra"], comm="sentra", hijos=(3, 4))
            proceso(proc, 3, cmdline=["python"])
            proceso(proc, 4, cmdline=["WebKitWebProcess"], hijos=(5,))
            proceso(proc, 5, cmdline=["x"])
            self.assertEqual(sorted(descendientes_en(proc, 1)), [2, 3, 4, 5])
            self.assertEqual(descendientes_en(proc, 99), [])

    def test_sentra_se_reconoce_por_el_nombre_de_su_proceso(self):
        from tests.humo_linux import es_sentra_en

        with TemporaryDirectory() as tmp:
            proc = Path(tmp)
            proceso(proc, 2, cmdline=["/r/target/release/sentra"], comm="sentra")
            proceso(proc, 3, cmdline=["/usr/bin/nosentra"], comm="nosentra")
            self.assertTrue(es_sentra_en(proc, 2))
            self.assertFalse(es_sentra_en(proc, 3))
            self.assertFalse(es_sentra_en(proc, 99))

    def test_un_proceso_terminado_o_zombi_ya_no_esta_vivo(self):
        from tests.humo_linux import vivo_en

        with TemporaryDirectory() as tmp:
            proc = Path(tmp)
            proceso(proc, 2, cmdline=["sentra"])
            proceso(proc, 3, cmdline=["sentra"], estado="Z")
            self.assertTrue(vivo_en(proc, 2))
            self.assertFalse(vivo_en(proc, 3))
            self.assertFalse(vivo_en(proc, 4))


class TestVigiaDelEscritorio(unittest.TestCase):
    """En Linux el humo corre en una pantalla virtual: en el escritorio de quien
    usa el ordenador no puede aparecer ninguna ventana de SENTRA, y menos con el foco."""

    def test_cuenta_las_ventanas_de_sentra_por_clase_o_por_proceso(self):
        from tests.humo_linux import ventanas_de_sentra

        clientes = [{"class": "kitty", "pid": 10}, {"class": "obsidian", "pid": 11},
                    {"class": "sentra", "pid": 12}, {"class": "", "pid": 13}]
        self.assertEqual(ventanas_de_sentra(clientes, lambda pid: pid == 13), 2)
        self.assertEqual(ventanas_de_sentra(clientes[:2], lambda pid: False), 0)
        self.assertEqual(ventanas_de_sentra([], lambda pid: True), 0)


class _ServidorFalso(BaseHTTPRequestHandler):
    peticiones: ClassVar[list[tuple[str, str, Any]]] = []

    def _responder(self, estado: int, valor: Any) -> None:
        cuerpo = json.dumps({"value": valor}).encode()
        self.send_response(estado)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_POST(self) -> None:
        datos = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        self.peticiones.append(("POST", self.path, datos))
        if self.path == "/session":
            self._responder(200, {"sessionId": "s1", "capabilities": {}})
        elif self.path == "/session/s1/execute/sync" and "throw" in datos["script"]:
            self._responder(500, {"error": "javascript error", "message": "x"})
        elif self.path == "/session/s1/execute/sync":
            self._responder(200, 42)
        else:
            self._responder(200, None)

    def do_DELETE(self) -> None:
        self.peticiones.append(("DELETE", self.path, None))
        self._responder(200, None)

    def log_message(self, *_: Any) -> None:
        pass


class TestClienteWebDriver(unittest.TestCase):
    def setUp(self):
        _ServidorFalso.peticiones = []
        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), _ServidorFalso)
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.addCleanup(self.servidor.server_close)
        self.addCleanup(self.servidor.shutdown)
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}"

    def test_abre_sesion_con_el_ejecutable_y_ejecuta_expresiones(self):
        from tests.humo_linux import WebDriver, capacidades

        wd = WebDriver(self.url)
        wd.abrir(capacidades(Path("/r/target/release/sentra")))
        self.assertEqual(wd.js("1 + 41"), 42)
        self.assertIsNone(wd.js("(() => { throw new Error('x'); })()"))
        wd.cerrar()
        metodo, ruta, datos = _ServidorFalso.peticiones[0]
        self.assertEqual((metodo, ruta), ("POST", "/session"))
        opciones = datos["capabilities"]["alwaysMatch"]["webkitgtk:browserOptions"]
        self.assertEqual(opciones["binary"], "/r/target/release/sentra")
        _, ruta, datos = _ServidorFalso.peticiones[1]
        self.assertEqual(ruta, "/session/s1/execute/sync")
        self.assertEqual(datos, {"script": "return (1 + 41);", "args": []})
        self.assertEqual(_ServidorFalso.peticiones[-1][:2], ("DELETE", "/session/s1"))

    def test_sin_servidor_no_cuelga_el_humo(self):
        from tests.humo_linux import WebDriver

        wd = WebDriver("http://127.0.0.1:9", espera=0.5)
        self.assertIsNone(wd.js("1"))


class TestPantallaOcupada(unittest.TestCase):
    def test_un_candado_o_un_socket_la_ocupan(self):
        from tests.humo_linux import PANTALLAS_DEL_HUMO, pantalla_ocupada

        self.assertNotIn(0, PANTALLAS_DEL_HUMO)
        with TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / ".X11-unix").mkdir()
            self.assertFalse(pantalla_ocupada(137, raiz))
            (raiz / ".X137-lock").write_text("1")
            self.assertTrue(pantalla_ocupada(137, raiz))
            (raiz / ".X138-lock").unlink(missing_ok=True)
            (raiz / ".X11-unix" / "X138").touch()
            self.assertTrue(pantalla_ocupada(138, raiz))


@unittest.skipUnless(shutil.which("Xvfb") and sys.platform == "linux", "sin Xvfb")
class TestPantallaVirtual(unittest.TestCase):
    def test_abre_una_pantalla_propia_y_la_recorre_sin_tocar_el_escritorio(self):
        from tests.humo_linux import cerrar_ventanas_x11, pantalla_virtual

        with pantalla_virtual() as display:
            self.assertRegex(display, r"^:\d+$")
            self.assertGreaterEqual(int(display[1:]), 90)
            self.assertNotEqual(display, os.environ.get("DISPLAY"))
            self.assertTrue(Path(f"/tmp/.X11-unix/X{display[1:]}").exists())
            # Ninguna ventana es de este pid: recorre el árbol y no manda nada.
            self.assertEqual(cerrar_ventanas_x11(display, os.getpid()), 0)
        self.assertFalse(Path(f"/tmp/.X11-unix/X{display[1:]}").exists())


class TestPlataformaLinux(unittest.TestCase):
    def test_dice_que_herramienta_falta_antes_de_empezar(self):
        from unittest import mock

        from tests.humo_linux import Linux

        with mock.patch("shutil.which", side_effect=lambda h: None if h == "WebKitWebDriver" else f"/usr/bin/{h}"):
            self.assertEqual(Linux().faltan(), ["WebKitWebDriver (paquete webkitgtk-6.0)"])
        with mock.patch("shutil.which", return_value="/usr/bin/x"):
            self.assertEqual(Linux().faltan(), [])

    def test_windows_no_pide_nada(self):
        from tests.humo_windows import Windows

        self.assertEqual(Windows().faltan(), [])

    def test_linux_es_la_plataforma_de_linux(self):
        from tests.humo_exe import plataforma_actual
        from tests.humo_linux import Linux

        plataforma = plataforma_actual("linux")
        self.assertIsInstance(plataforma, Linux)
        self.assertEqual(plataforma.exe_por_defecto.name, "sentra")


if __name__ == "__main__":
    unittest.main()
