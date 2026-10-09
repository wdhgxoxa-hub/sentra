"""
La prueba de humo en Windows: WebView2 y Win32
==============================================

La capa de Windows de `tests.humo_exe`: abre `sentra.exe` con la depuración
remota de WebView2 (CDP), cierra con WM_CLOSE a la ventana de la app o a la
ventana interna de tao, mata con taskkill, cuenta los motores con PowerShell
y vigila el primer plano con GetForegroundWindow. Lo que se comprueba y cómo
se evalúa está en `tests.humo_exe`, común a Windows y Linux.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Any, Self

from tests.humo_exe import RAIZ, VISTA_DEL_HUMO, AppControlada, entorno_discreto

EXE_POR_DEFECTO = RAIZ / "ui" / "src-tauri" / "target" / "release" / "sentra.exe"
PUERTO_CDP = 9337
#: El perfil de WebView que usa SENTRA de verdad (idioma y tema en su Local Storage).
PERFIL_REAL = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "com.sentra.desktop" / "EBWebView"
VENTANA_APP = "Tauri Window"
VENTANA_INTERNA = "Tao Thread Event Target"


def huella_perfil(carpeta: Path = PERFIL_REAL) -> str:
    """Huella de todo el Local Storage de un perfil de WebView ("" si no hay)."""
    h = hashlib.sha256()
    for f in sorted((carpeta / "Default" / "Local Storage").rglob("*")):
        if f.is_file():
            h.update(str(f.relative_to(carpeta)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


def entorno(perfil: Path | None, *, cdp: bool = False) -> dict[str, str]:
    """El entorno de la app: perfil de WebView aislado, modo discreto (la ventana no
    se ve ni roba el foco: ui/src-tauri/src/ventana.rs) y, si se pide, depuración remota."""
    valores = entorno_discreto()
    if perfil is not None:
        valores["WEBVIEW2_USER_DATA_FOLDER"] = str(perfil)
    if cdp:
        valores["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={PUERTO_CDP}"
    return valores


def _motores() -> int:
    """Procesos del motor vivos (el lanzador de la .venv y el intérprete)."""
    salida = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         ("@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object "
          "{ $_.CommandLine -match 'orchestration.sidecar_server' -and $_.CommandLine -match '--port 8765' }).Count")],
        capture_output=True, text=True, check=False)
    return int((salida.stdout or "0").strip() or 0)


class _Cdp(AppControlada):
    def __init__(self, exe: Path, perfil: Path | None = None) -> None:
        import websocket

        self.t0 = time.time()
        self.proceso = subprocess.Popen([str(exe)], cwd=str(exe.parent), env=entorno(perfil, cdp=True))
        self.pid = self.proceso.pid
        pagina = None
        for _ in range(120):
            time.sleep(0.25)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO_CDP}/json") as r:
                    pagina = next((p for p in json.load(r) if p.get("type") == "page"), None)
                if pagina:
                    break
            except OSError:
                pass
        if pagina is None:
            self.proceso.kill()
            raise RuntimeError("la ventana no expuso depuración remota")
        self.ws = websocket.create_connection(pagina["webSocketDebuggerUrl"], timeout=60, suppress_origin=True)
        self._n = 0
        self._respuestas: dict[int, dict[str, Any]] = {}
        self.excepciones: list[str] = []
        self.errores_csp = 0
        threading.Thread(target=self._leer, daemon=True).start()
        for dominio in ("Runtime.enable", "Log.enable"):
            self.enviar(dominio)
        ancho, alto = VISTA_DEL_HUMO
        self.enviar("Emulation.setDeviceMetricsOverride", width=ancho, height=alto, deviceScaleFactor=0, mobile=False)

    def _leer(self) -> None:
        import websocket

        while True:
            try:
                m = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue  # app en reposo: un rato sin mensajes no es una conexión cerrada
            except Exception:  # noqa: BLE001 - la conexión se cierra al cerrar la app
                return
            if "id" in m:
                self._respuestas[m["id"]] = m
            elif m.get("method") == "Runtime.exceptionThrown":
                d = m["params"]["exceptionDetails"]
                self.excepciones.append(str(d.get("exception", {}).get("description", d.get("text"))))
            elif m.get("method") == "Log.entryAdded" and "Content Security Policy" in m["params"]["entry"].get("text", ""):
                self.errores_csp += 1

    def enviar(self, metodo: str, **params: Any) -> dict[str, Any]:
        self._n += 1
        n = self._n
        self.ws.send(json.dumps({"id": n, "method": metodo, "params": params}))
        fin = time.time() + 30
        while time.time() < fin:
            if n in self._respuestas:
                return self._respuestas.pop(n)
            time.sleep(0.02)
        return {}

    def js(self, expresion: str) -> Any:
        r = self.enviar("Runtime.evaluate", expression=expresion, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("result", {}).get("value")

    def errores(self) -> tuple[list[str], int]:
        return list(self.excepciones), self.errores_csp

    def esperar_fin(self, limite: float) -> bool:
        try:
            self.proceso.wait(timeout=limite)
            return True
        except subprocess.TimeoutExpired:
            return False



def _ventana(pid: int, clase: str) -> int | None:
    """La ventana de nivel superior de `pid` con esa clase (EnumWindows)."""
    import ctypes
    import ctypes.wintypes as w

    if sys.platform != "win32":  # EnumWindows: solo Windows (y mypy lo sabe)
        raise OSError("EnumWindows solo existe en Windows")
    user32 = ctypes.windll.user32
    halladas: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)
    def cada(hwnd: int, _: int) -> bool:
        propio = w.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(propio))
        nombre = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, nombre, 256)
        if propio.value == pid and nombre.value == clase:
            halladas.append(hwnd)
        return True

    user32.EnumWindows(cada, 0)
    return halladas[0] if halladas else None


def _cerrar_ventana(pid: int, clase: str) -> bool:
    """WM_CLOSE a esa ventana, como la X (la de la app) o como taskkill cuando
    elige la ventana interna. taskkill sin /F no sirve: su destino cambia."""
    import ctypes

    if sys.platform != "win32":  # user32: solo Windows (y mypy lo sabe)
        raise OSError("user32 solo existe en Windows")
    hwnd = _ventana(pid, clase)
    return bool(hwnd) and bool(ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0))


class VigiaDePrimerPlano:
    """Cuenta, cada 100 ms, las muestras en que el primer plano es de sentra.exe."""

    def __init__(self) -> None:
        self.muestras = 0
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._vigilar, daemon=True)

    def __enter__(self) -> Self:
        self._hilo.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._parar.set()
        self._hilo.join(timeout=5)

    @staticmethod
    def es_de_sentra() -> bool:
        return VigiaDePrimerPlano.imagen_del_primer_plano().lower().endswith(r"\sentra.exe")

    @staticmethod
    def imagen_del_primer_plano() -> str:
        """Ruta del ejecutable dueño de la ventana en primer plano ('' si no se sabe)."""
        import ctypes
        from ctypes import wintypes

        if sys.platform != "win32":  # user32 y kernel32: solo Windows (y mypy lo sabe)
            raise OSError("user32 y kernel32 solo existen en Windows")
        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        ventana = u32.GetForegroundWindow()
        if not ventana:
            return ""
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(ventana, ctypes.byref(pid))
        proceso = k32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not proceso:
            return ""
        try:
            ruta = ctypes.create_unicode_buffer(1024)
            largo = wintypes.DWORD(1024)
            ok = k32.QueryFullProcessImageNameW(proceso, 0, ruta, ctypes.byref(largo))
            return ruta.value if ok else ""
        finally:
            k32.CloseHandle(proceso)

    def _vigilar(self) -> None:
        while not self._parar.wait(0.1):
            self.muestras += self.es_de_sentra()


class Windows:
    """La plataforma de `tests.humo_exe` en Windows."""

    exe_por_defecto = EXE_POR_DEFECTO

    def sesion(self) -> AbstractContextManager[object]:
        return nullcontext()

    def faltan(self) -> list[str]:
        return []

    def sentra_abierta(self) -> bool:
        abierta = subprocess.run(["tasklist", "/FI", "IMAGENAME eq sentra.exe"], capture_output=True, text=True, check=False)
        return "sentra.exe" in abierta.stdout.lower()

    def abrir(self, exe: Path, perfil: Path) -> AppControlada:
        return _Cdp(exe, perfil)

    def lanzar(self, exe: Path, perfil: Path) -> subprocess.Popen[bytes]:
        return subprocess.Popen([str(exe)], cwd=str(exe.parent), env=entorno(perfil))

    def cerrar_como_la_x(self, pid: int) -> None:
        _cerrar_ventana(pid, VENTANA_APP)

    def cerrar_por_dentro(self, proceso: subprocess.Popen[bytes]) -> None:
        """AUD2-027: WM_CLOSE a la ventana interna de tao."""
        _cerrar_ventana(proceso.pid, VENTANA_INTERNA)

    def matar(self, proceso: subprocess.Popen[bytes]) -> None:
        subprocess.run(["taskkill", "/F", "/PID", str(proceso.pid)], capture_output=True, check=False)

    def matar_arbol(self, pid: int) -> None:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)

    def motores(self) -> int:
        return _motores()

    def vigia(self) -> VigiaDePrimerPlano:
        return VigiaDePrimerPlano()

    def huella_perfil_real(self) -> str:
        return huella_perfil()

    def perfil_usado(self, perfil: Path) -> bool:
        return (perfil / "EBWebView").is_dir() or any(perfil.iterdir())
