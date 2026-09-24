"""
Prueba de humo del ejecutable real (AUD2-004)
============================================

    python -m tests.humo_exe [--exe RUTA] [--salida informe.json]

Lanza `sentra.exe` con la depuración remota de WebView2, lee lo que pinta
cada vista y lo compara con PostgreSQL en solo lectura: arranque en frío,
Radar, Búsqueda, Fuentes y Configuración con sus datos, sin excepciones ni
errores de CSP, cierre normal sin motores huérfanos y cierre forzado (como
un cuelgue) con el motor terminando solo y el puerto libre. No pulsa nada
que gaste Gemini o consulte fuentes, y comprueba que las preferencias del
usuario (idioma y tema, en el mismo perfil que usa él) no cambian.

Sale con 0 solo si no hay ningún fallo. Es el paso obligatorio previo a
toda release (README) y la compuerta lo ejecuta con HUMO=1: los 660 tests
en verde no vieron ni la pantalla negra ni las vistas vacías; esto sí.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
EXE_POR_DEFECTO = RAIZ / "ui" / "src-tauri" / "target" / "release" / "sentra.exe"
PUERTO_MOTOR = 8765
PUERTO_CDP = 9337

#: Límites de la interfaz: Top del juez (core/judge/store.py TOP_TARGET) y
#: evidencia reciente (ui/src/views/RadarView.tsx FEED_LIMIT).
TOP = 6
FEED = 40
#: Lo que puede tardar el motor en contestar (60 sondeos de 500 ms, sidecar.rs).
ARRANQUE_MAX_S = 30.0
#: El motor huérfano tiene que haber terminado tras un cierre forzado.
FIN_MOTOR_MAX_S = 10.0
#: Orígenes de la interfaz embebida en un exe de Tauri 2 (Windows usa el primero).
ORIGENES_EMBEBIDOS = ("http://tauri.localhost", "https://tauri.localhost", "tauri://localhost")


@dataclass(frozen=True)
class Verdad:
    """Lo que dice la base (solo lectura)."""

    veredictos_ultima: int
    evidencia_visible: int
    fuentes_catalogo: int
    hay_vectores: bool


@dataclass(frozen=True)
class Esperado:
    top: int
    resto: int
    feed: int


@dataclass
class Observado:
    """Lo que pinta la app real."""

    motor_activo_s: float | None = None
    radar_top: int = 0
    radar_resto: int = 0
    radar_feed: int = 0
    feed_fechas: list[str] = field(default_factory=list)
    feed_fuente_desconocida: int = 0
    busqueda_filas: int = 0
    fuentes_tarjetas: int = 0
    config_carga: bool = False
    excepciones: list[str] = field(default_factory=list)
    errores_csp: int = 0
    cierre_normal: bool = False
    huerfanos_tras_cierre: int = 0
    huerfanos_tras_matar: int = 0
    puerto_libre_tras_matar: bool = False
    preferencias_antes: dict[str, Any] | None = None
    preferencias_despues: dict[str, Any] | None = None
    #: AUD2-003: huella con la que se compiló la interfaz, la del motor que
    #: contesta y la carpeta desde la que corre.
    huella_compilada: str | None = None
    huella_motor: str | None = None
    raiz_motor: str | None = None
    #: Un exe de `cargo build` sin la feature custom-protocol abre el servidor de desarrollo.
    url_interfaz: str | None = None


def esperado(verdad: Verdad) -> Esperado:
    """El Top se llena hasta 6 sin rellenar; el resto va debajo; el feed recorta a 40."""
    return Esperado(top=min(TOP, verdad.veredictos_ultima),
                    resto=max(0, verdad.veredictos_ultima - TOP),
                    feed=min(FEED, verdad.evidencia_visible))


def evaluar(obs: Observado, verdad: Verdad, *, ahora: datetime) -> list[str]:
    """Fallos, en texto; lista vacía = la app hace lo que la base dice."""
    fallos: list[str] = []
    e = esperado(verdad)
    if not (obs.url_interfaz or "").startswith(ORIGENES_EMBEBIDOS):
        fallos.append(f"exe: la ventana abre {obs.url_interfaz}, no la interfaz embebida "
                      "(¿compilado con cargo en lugar de `npm run tauri build`?)")
    if obs.motor_activo_s is None or obs.motor_activo_s > ARRANQUE_MAX_S:
        fallos.append(f"motor: no quedó activo en {ARRANQUE_MAX_S:.0f} s ({obs.motor_activo_s})")
    if (obs.radar_top, obs.radar_resto) != (e.top, e.resto):
        fallos.append(f"radar: Top {obs.radar_top} y resto {obs.radar_resto}; la base dice {e.top} y {e.resto}")
    if obs.radar_feed != e.feed:
        fallos.append(f"radar: evidencia reciente {obs.radar_feed}; la base dice {e.feed}")
    limite = ahora.date().isoformat()
    futuras = [f for f in obs.feed_fechas if f > limite]
    if futuras:
        fallos.append(f"radar: {len(futuras)} evidencias con fecha futura ({futuras[0]})")
    if obs.feed_fuente_desconocida:
        fallos.append(f"radar: {obs.feed_fuente_desconocida} evidencias con fuente desconocida")
    if verdad.hay_vectores and obs.busqueda_filas == 0:
        fallos.append("búsqueda: 0 filas con vectores en la base")
    if obs.fuentes_tarjetas != verdad.fuentes_catalogo:
        fallos.append(f"fuentes: {obs.fuentes_tarjetas} tarjetas; el catálogo tiene {verdad.fuentes_catalogo}")
    if not obs.config_carga:
        fallos.append("configuración: no cargó")
    if obs.excepciones:
        fallos.append(f"consola: {len(obs.excepciones)} excepciones ({obs.excepciones[0][:120]})")
    if obs.errores_csp:
        fallos.append(f"consola: {obs.errores_csp} errores de CSP")
    if not obs.cierre_normal:
        fallos.append("cierre normal: la app no se cerró")
    if obs.huerfanos_tras_cierre:
        fallos.append(f"cierre normal: {obs.huerfanos_tras_cierre} motores vivos")
    if obs.huerfanos_tras_matar:
        fallos.append(f"cierre forzado: {obs.huerfanos_tras_matar} motores huérfanos")
    if not obs.puerto_libre_tras_matar:
        fallos.append(f"cierre forzado: el puerto {PUERTO_MOTOR} sigue ocupado")
    if not obs.huella_motor or obs.huella_motor != obs.huella_compilada:
        fallos.append(f"motor: huella {obs.huella_motor}; la interfaz se compiló con {obs.huella_compilada}")
    if obs.raiz_motor is None or _dentro_del_repo(obs.raiz_motor):
        fallos.append(f"motor: corre desde el repositorio ({obs.raiz_motor}), no desde su copia versionada")
    if obs.preferencias_antes != obs.preferencias_despues:
        fallos.append(f"preferencias del usuario cambiadas: {obs.preferencias_antes} → {obs.preferencias_despues}")
    return fallos


def _dentro_del_repo(ruta: str) -> bool:
    try:
        return Path(ruta).resolve().is_relative_to(RAIZ.resolve())
    except OSError:
        return False


# --- Verdad de la base (solo lectura) ---------------------------------------


def verdad_de_la_base() -> Verdad:
    import psycopg

    from core.sources.catalog import SOURCES
    from core.storage.postgres_store import resolver_dsn

    async def leer() -> Verdad:
        dsn = resolver_dsn()
        async with await psycopg.AsyncConnection.connect(dsn) as con:
            await con.set_read_only(True)
            cur = await con.execute(
                "SELECT count(*) FROM radar.niche_verdicts WHERE run_id = ("
                " SELECT run_id FROM radar.niche_verdicts ORDER BY created_at DESC LIMIT 1)")
            veredictos = (await cur.fetchone() or (0,))[0]
            cur = await con.execute("SELECT count(*) FROM radar.evidence_items")
            evidencia = (await cur.fetchone() or (0,))[0]
        from core.evidence.vectors import EvidenceVectorStore

        return Verdad(veredictos_ultima=int(veredictos), evidencia_visible=int(evidencia),
                      fuentes_catalogo=len(SOURCES), hay_vectores=EvidenceVectorStore().count() > 0)

    return asyncio.run(leer(), loop_factory=asyncio.SelectorEventLoop)


# --- La app real ------------------------------------------------------------


def _motores() -> int:
    """Procesos del motor vivos (el lanzador de la .venv y el intérprete)."""
    salida = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         ("@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object "
          "{ $_.CommandLine -match 'orchestration.sidecar_server' -and $_.CommandLine -match '--port 8765' }).Count")],
        capture_output=True, text=True, check=False)
    return int((salida.stdout or "0").strip() or 0)


def _puerto_ocupado(puerto: int = PUERTO_MOTOR) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", puerto)) == 0


class _Cdp:
    def __init__(self, exe: Path) -> None:
        import websocket

        entorno = dict(os.environ, WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=f"--remote-debugging-port={PUERTO_CDP}")
        self.t0 = time.time()
        self.proceso = subprocess.Popen([str(exe)], cwd=str(exe.parent), env=entorno)
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

    def _leer(self) -> None:
        while True:
            try:
                m = json.loads(self.ws.recv())
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

    def esperar(self, expresion: str, limite: float) -> bool:
        fin = time.time() + limite
        while time.time() < fin:
            if self.js(expresion):
                return True
            time.sleep(0.3)
        return False

    def ir(self, *etiquetas: str) -> None:
        self.js("(() => { const b = [...document.querySelectorAll('nav button')].find(x => "
                f"{json.dumps(list(etiquetas))}.some(e => x.innerText.trim().startsWith(e))); if (b) b.click(); }})()")


PREFERENCIAS = "(() => { try { return JSON.parse(localStorage.getItem('sentra.preferences')); } catch (e) { return null; } })()"


def recorrer(exe: Path) -> Observado:
    obs = Observado()
    app = _Cdp(exe)
    obs.url_interfaz = app.js("location.href")
    obs.preferencias_antes = app.js(PREFERENCIAS)
    if app.esperar("[...document.querySelectorAll('nav [title]')].some(d => /^(Motor|Engine)/.test(d.innerText.trim()) "
                   "&& /(activo|up)$/.test(d.innerText.replace(/\\s+/g, ' ').trim()))", ARRANQUE_MAX_S + 5):
        obs.motor_activo_s = round(time.time() - app.t0, 1)

    app.ir("Radar")
    app.esperar("document.querySelectorAll('section[aria-labelledby=top-juez] article').length > 0", 30)
    time.sleep(1)
    radar = app.js("""(() => {
      const feed = [...document.querySelectorAll('section[aria-labelledby=feed] li')];
      return {top: document.querySelectorAll('section[aria-labelledby=top-juez] article').length,
              resto: document.querySelectorAll('section[aria-labelledby=resto-veredictos] li').length,
              feed: feed.length,
              fechas: feed.map(li => { const t = li.querySelector('time'); return t ? t.getAttribute('dateTime').slice(0, 10) : ''; }),
              desconocida: feed.filter(li => /desconocida|unknown/i.test(li.innerText)).length};
    })()""") or {}
    obs.radar_top, obs.radar_resto, obs.radar_feed = radar.get("top", 0), radar.get("resto", 0), radar.get("feed", 0)
    obs.feed_fechas, obs.feed_fuente_desconocida = radar.get("fechas", []), radar.get("desconocida", 0)

    app.ir("Búsqueda", "Semantic", "Search")
    app.esperar("document.querySelector('main input')", 15)
    app.js("(() => { const i = document.querySelector('main input');"
           " const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;"
           " set.call(i, 'email notifications'); i.dispatchEvent(new Event('input', {bubbles: true})); })()")
    app.esperar("document.querySelectorAll('main tbody tr').length > 0 || document.querySelectorAll('main [role=alert]').length > 0", 30)
    obs.busqueda_filas = app.js("document.querySelectorAll('main tbody tr').length") or 0

    app.ir("Fuentes", "Sources")
    app.esperar("document.querySelectorAll('main .grid > article').length > 0", 20)
    obs.fuentes_tarjetas = app.js("document.querySelectorAll('main .grid > article').length") or 0

    app.ir("Configuración", "Settings")
    obs.config_carga = app.esperar("document.querySelectorAll('main select').length >= 1", 20)

    salud = app.js("window.__TAURI_INTERNALS__.invoke('get_app_health')") or {}
    info = salud.get("sidecarInfo") or {}
    obs.huella_compilada, obs.huella_motor, obs.raiz_motor = salud.get("motorBuild"), info.get("build"), info.get("codeRoot")

    obs.preferencias_despues = app.js(PREFERENCIAS)
    obs.excepciones, obs.errores_csp = list(app.excepciones), app.errores_csp

    subprocess.run(["taskkill", "/PID", str(app.proceso.pid)], capture_output=True, check=False)
    try:
        app.proceso.wait(timeout=20)
        obs.cierre_normal = True
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(app.proceso.pid)], capture_output=True, check=False)
    time.sleep(3)
    obs.huerfanos_tras_cierre = _motores()
    return obs


def matar_de_golpe(exe: Path, obs: Observado) -> None:
    """Como un cuelgue: se mata solo el exe; el motor tiene que terminar solo."""
    proceso = subprocess.Popen([str(exe)], cwd=str(exe.parent))
    fin = time.time() + ARRANQUE_MAX_S + 5
    while not _puerto_ocupado() and time.time() < fin:
        time.sleep(0.25)
    time.sleep(1)
    subprocess.run(["taskkill", "/F", "/PID", str(proceso.pid)], capture_output=True, check=False)
    fin = time.time() + FIN_MOTOR_MAX_S
    while time.time() < fin and (_puerto_ocupado() or _motores()):
        time.sleep(0.25)
    obs.huerfanos_tras_matar = _motores()
    obs.puerto_libre_tras_matar = not _puerto_ocupado()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prueba de humo del ejecutable real de SENTRA")
    parser.add_argument("--exe", type=Path, default=EXE_POR_DEFECTO)
    parser.add_argument("--salida", type=Path, default=None)
    args = parser.parse_args(argv)

    if not args.exe.is_file():
        print(f"HUMO FALLA: no existe {args.exe}")
        return 2
    abierta = subprocess.run(["tasklist", "/FI", "IMAGENAME eq sentra.exe"], capture_output=True, text=True, check=False)
    if "sentra.exe" in abierta.stdout.lower() or _puerto_ocupado():
        print("HUMO FALLA: SENTRA está abierta o el puerto 8765 está ocupado; ciérrala y repite")
        return 2

    verdad = verdad_de_la_base()
    obs = recorrer(args.exe)
    matar_de_golpe(args.exe, obs)
    fallos = evaluar(obs, verdad, ahora=datetime.now(UTC))
    informe = {"verdad": asdict(verdad), "esperado": asdict(esperado(verdad)), "observado": asdict(obs), "fallos": fallos}
    if args.salida:
        args.salida.write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")
    for fallo in fallos:
        print(f"  ✗ {fallo}")
    print(f"HUMO {'OK' if not fallos else 'FALLA'}: motor {obs.motor_activo_s} s · Top {obs.radar_top}+{obs.radar_resto} · "
          f"feed {obs.radar_feed} · búsqueda {obs.busqueda_filas} · fuentes {obs.fuentes_tarjetas} · "
          f"huérfanos {obs.huerfanos_tras_cierre}/{obs.huerfanos_tras_matar}")
    return 0 if not fallos else 1


if __name__ == "__main__":
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
