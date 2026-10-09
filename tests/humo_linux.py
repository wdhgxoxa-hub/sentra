"""
La prueba de humo en Linux: Xvfb, WebKitWebDriver y Hyprland
============================================================

La capa de Linux de `tests.humo_exe`. La app se abre dentro de una pantalla
virtual (Xvfb): no aparece en el escritorio ni puede quitarle el foco a quien
usa el ordenador, y además corre en modo discreto. Se controla con
WebKitWebDriver, el control remoto de WebKitGTK (`TAURI_WEBVIEW_AUTOMATION`
solo en esa apertura). Equivalencias con Windows:

- cerrar como la X: WM_DELETE_WINDOW a su ventana (lo que manda la X);
- cierre que no llega por la X: SIGTERM (cerrar sesión, apagar). La ventana
  interna de tao solo existe en Windows;
- cuelgue: SIGKILL solo a la app; el motor tiene que salir solo;
- motores y procesos: leídos de /proc (nunca `pgrep -f`, que se ve a sí mismo);
- foco: `hyprctl -j clients` cada 100 ms; ninguna ventana de SENTRA en el
  escritorio real;
- excepciones y CSP: `window.__sentraErrores` (ui/src/lib/vigia.ts).
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import signal
import socket
import subprocess
import threading
import time
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Any, Self

from tests.humo_exe import (
    PUERTO_MOTOR,
    RAIZ,
    VISTA_DEL_HUMO,
    AppControlada,
    entorno_discreto,
)

EXE_POR_DEFECTO = RAIZ / "ui" / "src-tauri" / "target" / "release" / "sentra"
PROC = Path("/proc")
#: Nombre del proceso de la app (comm) y clase de su ventana.
NOMBRE = "sentra"
MODULO_MOTOR = "core.orchestration.sidecar_server"
#: Variables que llevarían la app al escritorio real en lugar de a la pantalla virtual.
DEL_ESCRITORIO = ("WAYLAND_DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE")
#: Carpetas de datos de WebKit sin perfil propio y lo que en ellas es perfil del
#: usuario (Local Storage y compañía; no el motor ni los logs, que la app escribe
#: también durante el humo).
BASES_DEL_PERFIL_REAL = (NOMBRE, "com.sentra.desktop")
PARTES_DEL_PERFIL = ("localstorage", "storage", "databases", "indexeddb", "cookies")


def entorno(perfil: Path, display: str, *, automatizada: bool = False) -> dict[str, str]:
    """La app en la pantalla virtual, discreta y con su perfil aislado de WebKit."""
    valores = entorno_discreto()
    for variable in (*DEL_ESCRITORIO, "TAURI_WEBVIEW_AUTOMATION"):
        valores.pop(variable, None)
    valores.update({"DISPLAY": display, "GDK_BACKEND": "x11", "SENTRA_PERFIL_WEBVIEW": str(perfil)})
    if automatizada:
        valores["TAURI_WEBVIEW_AUTOMATION"] = "true"
    return valores


# --- /proc ------------------------------------------------------------------


def _leer(ruta: Path) -> str:
    try:
        return ruta.read_text("utf-8", errors="replace")
    except OSError:
        return ""


def _pids(proc: Path) -> Iterator[int]:
    try:
        return iter([int(d.name) for d in proc.iterdir() if d.name.isdigit()])
    except OSError:
        return iter([])


def vivo_en(proc: Path, pid: int) -> bool:
    """¿Existe y no es un zombi (ya terminó, aunque nadie lo haya recogido)?"""
    for linea in _leer(proc / str(pid) / "status").splitlines():
        if linea.startswith("State:"):
            return linea.split()[1] not in ("Z", "X")
    return False


def motores_en(proc: Path, puerto: int = PUERTO_MOTOR) -> int:
    """Motores vivos en el puerto del humo: un Python con el módulo del motor y `--port`."""
    n = 0
    for pid in _pids(proc):
        args = _leer(proc / str(pid) / "cmdline").split("\0")
        if (Path(args[0]).name.startswith("python") and MODULO_MOTOR in args
                and "--port" in args[:-1] and args[args.index("--port") + 1] == str(puerto)
                and vivo_en(proc, pid)):
            n += 1
    return n


def descendientes_en(proc: Path, pid: int) -> list[int]:
    """Todos los procesos que cuelgan de `pid` (hijos, nietos...)."""
    hallados: list[int] = []
    pendientes = [pid]
    while pendientes:
        actual = pendientes.pop()
        for hilo in (proc / str(actual) / "task").glob("*"):
            for hijo in _leer(hilo / "children").split():
                if int(hijo) not in hallados:
                    hallados.append(int(hijo))
                    pendientes.append(int(hijo))
    return hallados


def es_sentra_en(proc: Path, pid: int) -> bool:
    return _leer(proc / str(pid) / "comm").strip() == NOMBRE


# --- El escritorio real -----------------------------------------------------


def ventanas_de_sentra(clientes: list[dict[str, Any]], es_sentra: Callable[[int], bool]) -> int:
    """Ventanas de SENTRA entre las del escritorio (`hyprctl -j clients`)."""
    return sum(1 for c in clientes
               if str(c.get("class", "")).lower() == NOMBRE or es_sentra(int(c.get("pid", -1))))


class VigiaDelEscritorio:
    """Cuenta, cada 100 ms, las muestras con alguna ventana de SENTRA en el
    escritorio real (con foco o sin él): en el humo tiene que ser 0."""

    ORDEN = ("hyprctl", "-j", "clients")

    def __init__(self) -> None:
        self.muestras = 0
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._vigilar, daemon=True)

    def _clientes(self) -> list[dict[str, Any]]:
        salida = subprocess.run(self.ORDEN, capture_output=True, text=True, check=True, timeout=5)
        clientes = json.loads(salida.stdout)
        return clientes if isinstance(clientes, list) else []

    def __enter__(self) -> Self:
        try:
            self._clientes()
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            raise OSError(f"no se puede vigilar el escritorio sin hyprctl: {e}") from e
        self._hilo.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._parar.set()
        self._hilo.join(timeout=5)

    def _vigilar(self) -> None:
        while not self._parar.wait(0.1):
            try:
                clientes = self._clientes()
            except (OSError, ValueError, subprocess.SubprocessError):
                continue
            self.muestras += ventanas_de_sentra(clientes, lambda pid: es_sentra_en(PROC, pid)) > 0


# --- La pantalla virtual y la X ---------------------------------------------


#: Pantallas que puede usar el humo: lejos de :0 y de los primeros números, que
#: usan Xwayland y compañía. `-displayfd` no sirve: Xwayland escucha en un socket
#: abstracto que Xvfb no ve, y con un candado viejo Xvfb se quedaba con :0, la del
#: escritorio (medido el 09-10-2026).
PANTALLAS_DEL_HUMO = range(90, 140)


def pantalla_ocupada(numero: int, tmp: Path = Path("/tmp")) -> bool:
    """¿Hay algo en :numero? Candado, socket en fichero o socket abstracto."""
    if (tmp / f".X{numero}-lock").exists() or (tmp / ".X11-unix" / f"X{numero}").exists():
        return True
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        try:
            s.connect(f"\0/tmp/.X11-unix/X{numero}")
            return True
        except OSError:
            return False


@contextmanager
def pantalla_virtual() -> Iterator[str]:
    """Un Xvfb propio en una pantalla libre; devuelve su DISPLAY."""
    for numero in PANTALLAS_DEL_HUMO:
        if pantalla_ocupada(numero):
            continue
        xvfb = subprocess.Popen(["Xvfb", f":{numero}", "-screen", "0", "1440x900x24", "-nolisten", "tcp"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        fin = time.time() + 10
        while xvfb.poll() is None and not pantalla_ocupada(numero) and time.time() < fin:
            time.sleep(0.05)
        if xvfb.poll() is not None:
            continue  # otro la cogió a la vez: la siguiente
        try:
            yield f":{numero}"
        finally:
            xvfb.terminate()
            try:
                xvfb.wait(timeout=5)
            except subprocess.TimeoutExpired:
                xvfb.kill()
        return
    raise RuntimeError("no hay ninguna pantalla libre para Xvfb")


class _MensajeCliente(ctypes.Structure):
    """XClientMessageEvent."""

    _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong), ("send_event", ctypes.c_int),
                ("display", ctypes.c_void_p), ("window", ctypes.c_ulong), ("message_type", ctypes.c_ulong),
                ("format", ctypes.c_int), ("l", ctypes.c_long * 5)]


class _Evento(ctypes.Union):
    """XEvent: 24 longs, de los que el mensaje usa los primeros."""

    _fields_ = [("xclient", _MensajeCliente), ("pad", ctypes.c_long * 24)]


def _libx11() -> Any:
    x = ctypes.cdll.LoadLibrary("libX11.so.6")
    x.XOpenDisplay.restype = ctypes.c_void_p
    x.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x.XDefaultRootWindow.restype = ctypes.c_ulong
    x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x.XInternAtom.restype = ctypes.c_ulong
    x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x.XQueryTree.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                             ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),
                             ctypes.POINTER(ctypes.c_uint)]
    x.XGetWindowProperty.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long, ctypes.c_long,
                                     ctypes.c_int, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                                     ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong),
                                     ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_void_p)]
    x.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long, ctypes.c_void_p]
    x.XFree.argtypes = [ctypes.c_void_p]
    x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    x.XCloseDisplay.argtypes = [ctypes.c_void_p]
    return x


def _ventanas_x11(x: Any, dpy: int, raiz: int) -> list[int]:
    """Todas las ventanas bajo `raiz` (sin gestor de ventanas no hay marcos)."""
    halladas: list[int] = []
    pendientes = [raiz]
    while pendientes:
        actual = pendientes.pop()
        r, p, n = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_uint()
        hijos = ctypes.POINTER(ctypes.c_ulong)()
        if x.XQueryTree(dpy, actual, ctypes.byref(r), ctypes.byref(p), ctypes.byref(hijos), ctypes.byref(n)):
            nuevos = [hijos[i] for i in range(n.value)]
            if hijos:
                x.XFree(hijos)
            halladas += nuevos
            pendientes += nuevos
    return halladas


def _pid_de_ventana(x: Any, dpy: int, ventana: int, atomo_pid: int) -> int | None:
    tipo, formato = ctypes.c_ulong(), ctypes.c_int()
    n, resto, datos = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_void_p()
    if x.XGetWindowProperty(dpy, ventana, atomo_pid, 0, 1, 0, 6, ctypes.byref(tipo), ctypes.byref(formato),
                            ctypes.byref(n), ctypes.byref(resto), ctypes.byref(datos)) != 0 or not datos.value:
        return None
    try:
        return int(ctypes.cast(datos, ctypes.POINTER(ctypes.c_long))[0]) if n.value else None
    finally:
        x.XFree(datos)


def cerrar_ventanas_x11(display: str, pid: int) -> int:
    """WM_DELETE_WINDOW (lo que manda la X) a las ventanas de `pid` en `display`."""
    x = _libx11()
    dpy = x.XOpenDisplay(display.encode())
    if not dpy:
        return 0
    try:
        atomo_pid = x.XInternAtom(dpy, b"_NET_WM_PID", 0)
        protocolos = x.XInternAtom(dpy, b"WM_PROTOCOLS", 0)
        borrar = x.XInternAtom(dpy, b"WM_DELETE_WINDOW", 0)
        cerradas = 0
        for ventana in _ventanas_x11(x, dpy, x.XDefaultRootWindow(dpy)):
            if _pid_de_ventana(x, dpy, ventana, atomo_pid) != pid:
                continue
            evento = _Evento()
            evento.xclient.type, evento.xclient.send_event = 33, 1  # ClientMessage
            evento.xclient.display, evento.xclient.window = dpy, ventana
            evento.xclient.message_type, evento.xclient.format = protocolos, 32
            evento.xclient.l[0] = borrar
            cerradas += bool(x.XSendEvent(dpy, ventana, 0, 0, ctypes.byref(evento)))
        x.XSync(dpy, 0)
        return cerradas
    finally:
        x.XCloseDisplay(dpy)


# --- WebDriver --------------------------------------------------------------


def capacidades(exe: Path) -> dict[str, Any]:
    return {"alwaysMatch": {"webkitgtk:browserOptions": {"binary": str(exe), "args": []}}}


class WebDriver:
    """Cliente mínimo del protocolo WebDriver (HTTP y JSON) para WebKitWebDriver."""

    def __init__(self, url: str, *, espera: float = 30.0) -> None:
        self.url, self.espera = url, espera
        self.sesion: str | None = None

    def _pedir(self, metodo: str, ruta: str, datos: dict[str, Any] | None = None) -> Any:
        cuerpo = None if datos is None else json.dumps(datos).encode()
        peticion = urllib.request.Request(self.url + ruta, data=cuerpo, method=metodo,
                                          headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(peticion, timeout=self.espera) as r:
            return json.load(r).get("value")

    def listo(self) -> bool:
        """¿Contesta el driver? (antes de abrir sesión)."""
        try:
            return self._pedir("GET", "/status") is not None
        except (OSError, ValueError):
            return False

    def abrir(self, capacidades_: dict[str, Any]) -> None:
        self.sesion = self._pedir("POST", "/session", {"capabilities": capacidades_})["sessionId"]

    def js(self, expresion: str) -> Any:
        """El valor de una expresión (las promesas se esperan); None si falla."""
        try:
            return self._pedir("POST", f"/session/{self.sesion}/execute/sync",
                               {"script": f"return ({expresion});", "args": []})
        except (OSError, ValueError):
            return None

    def tamano(self, ancho: int, alto: int) -> None:
        try:
            self._pedir("POST", f"/session/{self.sesion}/window/rect", {"width": ancho, "height": alto})
        except (OSError, ValueError):
            pass

    def cerrar(self) -> None:
        if self.sesion is not None:
            try:
                self._pedir("DELETE", f"/session/{self.sesion}")
            except (OSError, ValueError):
                pass
            self.sesion = None


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _AppWebDriver(AppControlada):
    def __init__(self, exe: Path, perfil: Path, display: str) -> None:
        puerto = _puerto_libre()
        self.t0 = time.time()
        self.driver = subprocess.Popen(["WebKitWebDriver", f"--port={puerto}"],
                                       env=entorno(perfil, display, automatizada=True),
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.wd = WebDriver(f"http://127.0.0.1:{puerto}", espera=60)
        fin = time.time() + 10
        while not self.wd.listo() and time.time() < fin:
            time.sleep(0.1)
        try:
            self.wd.abrir(capacidades(exe))
        except (OSError, ValueError, KeyError, TypeError) as e:
            self.driver.kill()
            raise RuntimeError(f"WebKitWebDriver no abrió la app: {e}") from e
        sentras = [p for p in descendientes_en(PROC, self.driver.pid) if es_sentra_en(PROC, p)]
        if not sentras:
            self.soltar()
            raise RuntimeError("WebKitWebDriver abrió una sesión pero no hay proceso sentra")
        self.pid = sentras[0]
        self.wd.tamano(*VISTA_DEL_HUMO)

    def js(self, expresion: str) -> Any:
        return self.wd.js(expresion)

    def errores(self) -> tuple[list[str], int]:
        vistos = self.js("window.__sentraErrores ?? null")
        if not isinstance(vistos, dict):
            return ["la interfaz no tiene el vigía de errores (window.__sentraErrores)"], 0
        return [str(e) for e in vistos.get("excepciones", [])], int(vistos.get("csp", 0))

    def esperar_fin(self, limite: float) -> bool:
        fin = time.time() + limite
        while vivo_en(PROC, self.pid):
            if time.time() > fin:
                return False
            time.sleep(0.2)
        return True

    def soltar(self) -> None:
        self.wd.cerrar()
        self.driver.terminate()
        try:
            self.driver.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.driver.kill()


# --- La plataforma ----------------------------------------------------------


def huella_perfil_real(datos: Path | None = None) -> str:
    """Huella del perfil de WebKit que usa SENTRA sin perfil propio ("" si no hay)."""
    datos = datos or Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    h = hashlib.sha256()
    for base in BASES_DEL_PERFIL_REAL:
        for parte in PARTES_DEL_PERFIL:
            raiz = datos / base / parte
            for f in sorted([raiz] if raiz.is_file() else raiz.rglob("*")):
                if f.is_file():
                    h.update(str(f.relative_to(datos)).encode())
                    h.update(f.read_bytes())
    return h.hexdigest()[:16]


class Linux:
    """La plataforma de `tests.humo_exe` en Linux."""

    exe_por_defecto = EXE_POR_DEFECTO

    def __init__(self) -> None:
        self.display = ""

    def sesion(self) -> AbstractContextManager[object]:
        @contextmanager
        def en_marcha() -> Iterator[str]:
            with pantalla_virtual() as display:
                self.display = display
                yield display

        return en_marcha()

    def sentra_abierta(self) -> bool:
        return any(es_sentra_en(PROC, p) and vivo_en(PROC, p) for p in _pids(PROC))

    def abrir(self, exe: Path, perfil: Path) -> AppControlada:
        return _AppWebDriver(exe, perfil, self.display)

    def lanzar(self, exe: Path, perfil: Path) -> subprocess.Popen[bytes]:
        return subprocess.Popen([str(exe)], cwd=str(exe.parent), env=entorno(perfil, self.display),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def cerrar_como_la_x(self, pid: int) -> None:
        cerrar_ventanas_x11(self.display, pid)

    def cerrar_por_dentro(self, proceso: subprocess.Popen[bytes]) -> None:
        """La ventana interna de tao solo existe en Windows: en Linux, SIGTERM."""
        proceso.send_signal(signal.SIGTERM)

    def matar(self, proceso: subprocess.Popen[bytes]) -> None:
        proceso.kill()

    def matar_arbol(self, pid: int) -> None:
        for p in [pid, *descendientes_en(PROC, pid)]:
            try:
                os.kill(p, signal.SIGKILL)
            except OSError:
                pass

    def motores(self) -> int:
        return motores_en(PROC)

    def vigia(self) -> VigiaDelEscritorio:
        return VigiaDelEscritorio()

    def huella_perfil_real(self) -> str:
        return huella_perfil_real()

    def perfil_usado(self, perfil: Path) -> bool:
        return perfil.is_dir() and any(perfil.iterdir())
