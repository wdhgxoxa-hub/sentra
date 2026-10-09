"""
Prueba de humo del ejecutable real (AUD2-004)
============================================

    python -m tests.humo_exe [--exe RUTA] [--salida informe.json]

Lanza el ejecutable real con un control remoto del WebView, lee lo que pinta
cada vista y lo compara con PostgreSQL en solo lectura: arranque en frío,
Radar, Búsqueda, Fuentes y Configuración con sus datos, sin excepciones ni
errores de CSP, cierre normal sin motores huérfanos y cierre forzado (como
un cuelgue) con el motor terminando solo y el puerto libre. No pulsa nada
que gaste Gemini o consulte fuentes. La app corre con un perfil de WebView
aislado y temporal: el perfil real del usuario (idioma, tema) no se toca, y
la prueba falla si cambiara un solo byte.

Aquí está lo común: qué se mira en cada pantalla y cómo se evalúa. Lo que
depende del sistema (cómo se abre, se cierra y se mata la app, cómo se
cuentan los motores y se vigila el foco) va en una `Plataforma`:
`tests/humo_windows.py` (WebView2 y Win32) y `tests/humo_linux.py`.

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
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

RAIZ = Path(__file__).resolve().parents[1]
PUERTO_MOTOR = 8765

#: Límite de la evidencia reciente (ui/src/views/RadarView.tsx FEED_LIMIT).
FEED = 40
#: Lo que puede tardar el motor en contestar (60 sondeos de 500 ms, sidecar.rs).
ARRANQUE_MAX_S = 30.0
#: El motor huérfano tiene que haber terminado tras un cierre forzado.
FIN_MOTOR_MAX_S = 10.0
#: Lo que se espera a la búsqueda: más que la propia app (SEARCH_TIMEOUT, 60 s en
#: commands/engine.rs). La primera búsqueda tras compilar carga e5 en frío y con
#: 30 s el humo daba un falso rojo que la app no tenía.
BUSQUEDA_MAX_S = 65.0
#: Orígenes de la interfaz embebida en un exe de Tauri 2 (Windows usa el primero).
ORIGENES_EMBEBIDOS = ("http://tauri.localhost", "https://tauri.localhost", "tauri://localhost")
#: WebView2 abre la página en blanco y luego navega: lo que se espera a esa
#: navegación antes de dar por buena la URL que haya.
URL_MAX_S = 10.0
_SIN_NAVEGAR = (None, "", "about:blank")


@dataclass(frozen=True)
class Verdad:
    """Lo que dice la base (solo lectura)."""

    veredictos_ultima: int
    evidencia_visible: int
    fuentes_catalogo: int
    hay_vectores: bool
    #: Fase 2: de esos veredictos, los que no son DESCARTAR; y si el último
    #: escaneo juzgado no es el que se enseña (el Radar lo avisa).
    nichos_ultima: int = 0
    aviso_ultimo: bool = False


@dataclass(frozen=True)
class Esperado:
    nichos: int
    descartados: int
    feed: int


@dataclass
class Observado:
    """Lo que pinta la app real."""

    motor_activo_s: float | None = None
    radar_nichos: int = 0
    radar_descartados: int = 0
    #: El caso del resultado que abre el aviso del Radar (None si no se abrió) y
    #: si la ficha del primer nicho se abre.
    resultado_desde_aviso: str | None = None
    ficha_abre: bool = False
    radar_feed: int = 0
    feed_fechas: list[str] = field(default_factory=list)
    feed_fuente_desconocida: int = 0
    busqueda_filas: int = 0
    busqueda_s: float | None = None
    fuentes_tarjetas: int = 0
    config_carga: bool = False
    excepciones: list[str] = field(default_factory=list)
    errores_csp: int = 0
    cierre_normal: bool = False
    huerfanos_tras_cierre: int = 0
    huerfanos_tras_matar: int = 0
    #: Walter (Fase 3): muestras (cada 100 ms, las tres aperturas) en las que una
    #: ventana de SENTRA, visible u oculta, tenía el primer plano: 0.
    primer_plano: int = 0
    puerto_libre_tras_matar: bool = False
    #: Huella del Local Storage del perfil real antes y después, y si la app
    #: escribió en el perfil aislado (si no, habría vuelto al real).
    perfil_real_antes: str | None = None
    perfil_real_despues: str | None = None
    perfil_aislado_usado: bool = False
    #: AUD2-003: huella con la que se compiló la interfaz, la del motor que
    #: contesta y la carpeta desde la que corre.
    huella_compilada: str | None = None
    huella_motor: str | None = None
    raiz_motor: str | None = None
    #: Un exe de `cargo build` sin la feature custom-protocol abre el servidor de desarrollo.
    url_interfaz: str | None = None
    #: AUD2-027: un WM_CLOSE a la ventana interna de tao («Tao Thread Event Target»,
    #: visible a propósito) no puede dejar el proceso colgado ni motores vivos.
    cierre_ventana_interna: bool = False
    huerfanos_tras_ventana_interna: int = 0
    #: Filas que aparecieron en llm_usage (base real) mientras corría la app: 0.
    uso_gemini_nuevo: int = 0
    #: Fase 2: la pantalla con la que arranca («nuevo»), cuántas acciones
    #: principales tiene cada pantalla nueva (1), la jerga visible de cada una
    #: (tests/_lenguaje_llano.py; los «Ver detalle» cerrados no cuentan) y si el
    #: asistente pasa del tema a las palabras sin gastar.
    pantalla_inicial: str | None = None
    acciones_principales: dict[str, int] = field(default_factory=dict)
    jerga: dict[str, list[str]] = field(default_factory=dict)
    #: R9 (Fase 3): identificadores de autor visibles en cada pantalla (DID,
    #: at://, @usuario), con los «Ver detalle» abiertos y el texto ajeno incluido,
    #: también dentro de una dirección (D-M12).
    identificadores: dict[str, list[str]] = field(default_factory=dict)
    #: Fase 3: cuántos px se sale la pantalla por la derecha con cada texto ajeno
    #: sustituido por uno largo sin espacios (0: todo se parte).
    desborde: dict[str, int] = field(default_factory=dict)
    asistente_paso2: bool = False


def esperado(verdad: Verdad) -> Esperado:
    """Fase 2: el Radar enseña todos los veredictos de la ejecución con nichos,
    los nichos a la vista y los descartados plegados; el feed recorta a 40."""
    return Esperado(nichos=verdad.nichos_ultima,
                    descartados=verdad.veredictos_ultima - verdad.nichos_ultima,
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
    if (obs.radar_nichos, obs.radar_descartados) != (e.nichos, e.descartados):
        fallos.append(f"radar: {obs.radar_nichos} nichos y {obs.radar_descartados} descartados; "
                      f"la base dice {e.nichos} y {e.descartados}")
    if verdad.aviso_ultimo and obs.resultado_desde_aviso is None:
        fallos.append("radar: el aviso del último escaneo no enseña su resultado")
    if e.nichos and not obs.ficha_abre:
        fallos.append("radar: la ficha del primer nicho no se abre")
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
    if obs.primer_plano:
        fallos.append(f"foco: una ventana de SENTRA tuvo el primer plano en {obs.primer_plano} muestras; "
                      "el humo no puede quitarle el foco a quien usa el ordenador")
    if not obs.puerto_libre_tras_matar:
        fallos.append(f"cierre forzado: el puerto {PUERTO_MOTOR} sigue ocupado")
    if not obs.cierre_ventana_interna:
        fallos.append("cierre por la ventana interna de tao: el proceso no terminó")
    if obs.huerfanos_tras_ventana_interna:
        fallos.append(f"cierre por la ventana interna de tao: {obs.huerfanos_tras_ventana_interna} motores vivos")
    if not obs.huella_motor or obs.huella_motor != obs.huella_compilada:
        fallos.append(f"motor: huella {obs.huella_motor}; la interfaz se compiló con {obs.huella_compilada}")
    if obs.raiz_motor is None or _dentro_del_repo(obs.raiz_motor):
        fallos.append(f"motor: corre desde el repositorio ({obs.raiz_motor}), no desde su copia versionada")
    if obs.perfil_real_antes != obs.perfil_real_despues:
        fallos.append(f"perfil real del usuario cambiado: {obs.perfil_real_antes} → {obs.perfil_real_despues}")
    if not obs.perfil_aislado_usado:
        fallos.append("perfil aislado: la app no lo usó (¿ignoró la variable del perfil aislado?)")
    if obs.pantalla_inicial != "nuevo":
        fallos.append(f"inicio: la app arranca en «{obs.pantalla_inicial}», no en Nuevo escaneo")
    for pantalla, n in obs.acciones_principales.items():
        if n != 1:
            fallos.append(f"{pantalla}: {n} acciones principales; tiene que haber una sola acción principal")
    for pantalla, palabras in obs.jerga.items():
        if palabras:
            fallos.append(f"{pantalla}: jerga visible ({', '.join(palabras)})")
    for pantalla, px in obs.desborde.items():
        if px > 1:
            fallos.append(f"{pantalla}: un texto largo empuja la pantalla {px} px hacia la derecha; tiene que partirse")
    for pantalla, ids in obs.identificadores.items():
        if ids:
            fallos.append(f"{pantalla}: identificadores de autor visibles, R9 ({', '.join(ids[:3])})")
    if not obs.asistente_paso2:
        fallos.append("asistente: no pasa del tema a las palabras clave")
    if obs.uso_gemini_nuevo:
        fallos.append(f"Gemini: la app llamó a Google durante el humo ({obs.uso_gemini_nuevo} filas nuevas "
                      "en llm_usage); el humo no puede gastar ni registrar llamadas")
    return fallos



def _dentro_del_repo(ruta: str) -> bool:
    try:
        return Path(ruta).resolve().is_relative_to(RAIZ.resolve())
    except OSError:
        return False


# --- Verdad de la base (solo lectura) ---------------------------------------


async def lo_que_ensena_el_radar(store: Any) -> tuple[int, int, bool]:
    """(veredictos, nichos, aviso) de la ejecución que enseña el Radar, con la
    misma regla que la app (`leer_radar`): la última con nichos y, si no hay, la
    última juzgada. `aviso`: la última juzgada es otra (el Radar lo dice)."""
    from core.judge.store import latest_judged_run, latest_run_with_niches

    ultima = await latest_judged_run(store)
    ejecucion = await latest_run_with_niches(store) or ultima
    if ejecucion is None:
        return 0, 0, False
    fila = await store._fetchone(
        "SELECT count(*) AS n, count(*) FILTER (WHERE verdict <> 'DESCARTAR') AS nichos "
        "FROM niche_verdicts WHERE tenant_id = %s AND run_id = %s",
        (store.tenant_id, ejecucion))
    return (int(fila["n"]), int(fila["nichos"]), ultima is not None and ultima != ejecucion) if fila else (0, 0, False)


async def veredictos_de_la_ultima_juzgada(store: Any) -> int:
    """Los veredictos de la ejecución que enseña el Radar (ver `lo_que_ensena_el_radar`)."""
    return (await lo_que_ensena_el_radar(store))[0]


def verdad_de_la_base() -> Verdad:
    import psycopg

    from core.sources.catalog import SOURCES
    from core.storage.postgres_store import PostgresStore, resolver_dsn

    async def leer() -> Verdad:
        dsn = resolver_dsn()
        async with await psycopg.AsyncConnection.connect(dsn) as con:
            await con.set_read_only(True)
            cur = await con.execute("SELECT count(*) FROM radar.evidence_items")
            evidencia = (await cur.fetchone() or (0,))[0]
        async with PostgresStore(dsn=dsn) as store:
            await store.connection.set_read_only(True)
            veredictos, nichos, aviso = await lo_que_ensena_el_radar(store)
        from core.evidence.vectors import EvidenceVectorStore

        return Verdad(veredictos_ultima=veredictos, evidencia_visible=int(evidencia),
                      fuentes_catalogo=len(SOURCES), hay_vectores=EvidenceVectorStore().count() > 0,
                      nichos_ultima=nichos, aviso_ultimo=aviso)

    return asyncio.run(leer(), loop_factory=asyncio.SelectorEventLoop)


def contar_uso_gemini() -> int:
    """Filas de llm_usage en la base real (solo lectura)."""
    import psycopg

    from core.storage.postgres_store import resolver_dsn

    with psycopg.connect(resolver_dsn()) as con:
        con.read_only = True
        fila = con.execute("SELECT count(*) FROM radar.llm_usage").fetchone()
    return int(fila[0]) if fila else 0


def preparar_cache_modelos(origen: Path, destino: Path, *, ahora: float) -> int:
    """La caché de modelos de Gemini del humo: las entradas de la real con la
    hora de ahora. Con ella el motor no pide la lista a Google aunque la real
    haya caducado. Devuelve cuántas entradas copió (sin caché real, 0: si el
    motor llamara a Google, el recuento de llm_usage lo delataría)."""
    try:
        real = json.loads(origen.read_text("utf-8"))
    except (OSError, ValueError):
        real = {}
    fresca = {huella: {**entrada, "listed_at": ahora} for huella, entrada in real.items()
              if isinstance(entrada, dict) and "models" in entrada}
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(fresca), "utf-8")
    return len(fresca)


# --- La app real ------------------------------------------------------------


def _puerto_ocupado(puerto: int = PUERTO_MOTOR) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def entorno_discreto() -> dict[str, str]:
    """El entorno de la app en el humo: modo discreto (la ventana no se ve ni roba
    el foco: ui/src-tauri/src/ventana.rs). Cada plataforma añade el resto."""
    valores = dict(os.environ)
    valores["SENTRA_VENTANA_DISCRETA"] = "1"
    return valores


class AppControlada:
    """La app abierta con un control remoto del WebView (CDP en Windows,
    WebDriver en Linux): basta con que sepa ejecutar JavaScript."""

    t0: float
    pid: int

    def js(self, expresion: str) -> Any:
        raise NotImplementedError

    def errores(self) -> tuple[list[str], int]:
        """Excepciones sin capturar y errores de CSP vistos hasta ahora."""
        raise NotImplementedError

    def esperar_fin(self, limite: float) -> bool:
        """¿Terminó el proceso de la app antes de `limite` segundos?"""
        raise NotImplementedError

    def soltar(self) -> None:
        """Suelta el control remoto cuando la app ya se cerró."""

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


class Vigia(Protocol):
    """Cuenta las muestras en que una ventana de SENTRA tuvo el foco."""

    muestras: int

    def __enter__(self) -> Any: ...

    def __exit__(self, *_: object) -> None: ...


class Plataforma(Protocol):
    """Lo que depende del sistema; lo que se comprueba es común (evaluar)."""

    exe_por_defecto: Path

    def sesion(self) -> AbstractContextManager[object]:
        """Lo que tiene que estar en marcha durante todo el humo (en Linux, la
        pantalla virtual)."""
        ...

    def sentra_abierta(self) -> bool: ...

    def abrir(self, exe: Path, perfil: Path) -> AppControlada: ...

    def lanzar(self, exe: Path, perfil: Path) -> subprocess.Popen[bytes]: ...

    def cerrar_como_la_x(self, pid: int) -> None: ...

    def cerrar_por_dentro(self, proceso: subprocess.Popen[bytes]) -> None:
        """El cierre que no llega por la X: la ventana interna de tao en Windows."""
        ...

    def matar(self, proceso: subprocess.Popen[bytes]) -> None:
        """Como un cuelgue: solo la app, sin dejarle cerrar nada."""
        ...

    def matar_arbol(self, pid: int) -> None: ...

    def motores(self) -> int:
        """Procesos del motor vivos en el puerto del humo."""
        ...

    def vigia(self) -> Vigia: ...

    def huella_perfil_real(self) -> str: ...

    def perfil_usado(self, perfil: Path) -> bool: ...


def plataforma_actual(sistema: str = sys.platform) -> Plataforma:
    if sistema == "win32":
        from tests.humo_windows import Windows

        return Windows()
    if sistema == "linux":
        from tests.humo_linux import Linux

        return Linux()
    raise OSError(f"el humo no sabe abrir la app en {sistema}")


#: Vista con la que el humo mira la app: el mínimo de la ventana (tauri.conf.json).
#: Oculta mide 1440 y visible lo que decida el gestor de ventanas; fijada, el
#: resultado no depende de eso y el desborde se mide en el caso más estrecho.
VISTA_DEL_HUMO = (960, 600)


def url_de_la_interfaz(
    leer: Callable[[], str | None], *, limite: float = URL_MAX_S,
    reloj: Callable[[], float] = time.monotonic, dormir: Callable[[float], None] = time.sleep,
) -> str | None:
    """La URL de la ventana cuando WebView2 ya ha navegado.

    Nada más conectarse por CDP la página puede seguir en `about:blank`: leerla
    entonces daba un falso «sin interfaz embebida» con la app sana. Se espera a
    que navegue; si no navega en `limite`, se devuelve la última URL leída y
    evaluar() la marca como fallo.
    """
    fin = reloj() + limite
    url = leer()
    while url in _SIN_NAVEGAR and reloj() < fin:
        dormir(0.25)
        url = leer()
    return url


#: Texto visible de la pantalla sin lo marcado como ajeno (se oculta un
#: instante para que innerText, que respeta lo pintado, no lo cuente).
TEXTO_PROPIO = """(() => {
  const main = document.querySelector('main');
  if (!main) return '';
  const ajenos = [...main.querySelectorAll('[data-ajeno]')];
  const antes = ajenos.map((e) => e.style.display);
  ajenos.forEach((e) => { e.style.display = 'none'; });
  const texto = main.innerText;
  ajenos.forEach((e, i) => { e.style.display = antes[i]; });
  return texto;
})()"""


#: Todo el texto visible de la pantalla con cada «Ver detalle» abierto un
#: instante (para R9 cuentan también el detalle y el texto ajeno).
TEXTO_COMPLETO = """(() => {
  const main = document.querySelector('main');
  if (!main) return '';
  const cerrados = [...main.querySelectorAll('details:not([open])')];
  cerrados.forEach((d) => { d.open = true; });
  const texto = main.innerText;
  cerrados.forEach((d) => { d.open = false; });
  return texto;
})()"""


#: Cada texto ajeno sustituido un instante por uno largo sin espacios (como la
#: clave de un grupo de Bluesky): cuántos px se sale algo por la derecha de main.
DESBORDE_CON_TEXTO_LARGO = """(() => {
  const main = document.querySelector('main');
  if (!main) return 0;
  const ajenos = [...main.querySelectorAll('[data-ajeno]')].filter((e) => e.children.length === 0);
  const antes = ajenos.map((e) => e.textContent);
  ajenos.forEach((e) => { e.textContent = 'bluesky:did:plc:' + 'x'.repeat(200); });
  const borde = main.getBoundingClientRect().right;
  const px = Math.max(0, ...[...main.querySelectorAll('*')].map((e) => e.getBoundingClientRect().right - borde));
  ajenos.forEach((e, i) => { e.textContent = antes[i]; });
  return Math.round(px);
})()"""


def identificadores_visibles(texto: str) -> list[str]:
    """Los identificadores de autor (R9) de un texto visible, también dentro de una
    dirección. D-M12: la dirección completa, con el DID de Bluesky, solo va en el
    destino de «Copiar dirección» (un atributo, no texto)."""
    from core.privacidad import IDENTIFICADOR_DE_AUTOR

    return IDENTIFICADOR_DE_AUTOR.findall(texto)


def _pantalla_llana(app: AppControlada, obs: Observado, nombre: str, *, accion_principal: bool = True) -> None:
    """P1 en la pantalla abierta: qué jerga se ve (innerText no incluye lo que
    hay dentro de un «Ver detalle» cerrado) y, en las pantallas con acción
    principal (asistente, Radar, ficha), cuántas hay."""
    from tests._lenguaje_llano import palabras_prohibidas

    if accion_principal:
        obs.acciones_principales[nombre] = app.js("document.querySelectorAll('main [data-accion-principal]').length") or 0
    # Lo que no es texto de SENTRA (citas de la evidencia, nombres de nichos)
    # va marcado con data-ajeno y no cuenta: son datos y se enseñan tal cual.
    obs.jerga[nombre] = palabras_prohibidas(app.js(TEXTO_PROPIO) or "")
    obs.identificadores[nombre] = identificadores_visibles(app.js(TEXTO_COMPLETO) or "")
    obs.desborde[nombre] = app.js(DESBORDE_CON_TEXTO_LARGO) or 0


def recorrer(plat: Plataforma, exe: Path, perfil: Path) -> Observado:
    obs = Observado()
    app = plat.abrir(exe, perfil)
    obs.url_interfaz = url_de_la_interfaz(lambda: app.js("location.href"))
    if app.esperar("[...document.querySelectorAll('nav [title]')].some(d => /^(Motor|Engine)/.test(d.innerText.trim()) "
                   "&& /(activo|up)$/.test(d.innerText.replace(/\\s+/g, ' ').trim()))", ARRANQUE_MAX_S + 5):
        obs.motor_activo_s = round(time.time() - app.t0, 1)

    # Fase 2: arranca en «Nuevo escaneo»; el asistente pasa al paso 2 sin gastar.
    # `!!`: un nodo llega por CDP como {} y en Python {} es falso (espera vacua).
    app.esperar("!!document.querySelector('[data-pantalla=nuevo]')", 20)
    obs.pantalla_inicial = app.js("document.querySelector('nav [aria-current=page]')?.dataset.vista ?? null")
    _pantalla_llana(app, obs, "nuevo")
    app.js("(() => { const i = document.querySelector('[data-campo=tema]');"
           " const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;"
           " set.call(i, 'clientes que pagan tarde'); i.dispatchEvent(new Event('input', {bubbles: true})); })()")
    app.js("document.querySelector('main [data-accion-principal]')?.click()")
    obs.asistente_paso2 = app.esperar("!!document.querySelector('[data-pantalla=nuevo][data-paso=\"2\"]')", 10)
    if obs.asistente_paso2:
        _pantalla_llana(app, obs, "nuevo, paso 2")

    app.ir("Radar")
    app.esperar("!!document.querySelector('[data-pantalla=radar]') && "
                "(document.querySelectorAll('[data-nicho], [data-descartado]').length > 0 || "
                "document.querySelector('main').innerText.length > 200)", 30)
    app.esperar("document.querySelectorAll('[data-evidencia]').length > 0", 15)
    time.sleep(1)
    _pantalla_llana(app, obs, "radar")
    radar = app.js("""(() => {
      const feed = [...document.querySelectorAll('[data-evidencia]')];
      return {nichos: document.querySelectorAll('[data-pantalla=radar] [data-nicho]').length,
              descartados: document.querySelectorAll('[data-pantalla=radar] [data-descartado]').length,
              feed: feed.length,
              fechas: feed.map(li => { const t = li.querySelector('time'); return t ? t.getAttribute('dateTime').slice(0, 10) : ''; }),
              desconocida: feed.filter(li => /desconocida|unknown/i.test(li.innerText)).length};
    })()""") or {}
    obs.radar_nichos, obs.radar_descartados = radar.get("nichos", 0), radar.get("descartados", 0)
    obs.radar_feed = radar.get("feed", 0)
    obs.feed_fechas, obs.feed_fuente_desconocida = radar.get("fechas", []), radar.get("desconocida", 0)
    # El aviso del último escaneo enseña su resultado (lee la base; no gasta).
    if app.js("!!document.querySelector('[data-aviso-ultimo] button')"):
        app.js("document.querySelector('[data-aviso-ultimo] button').click()")
        if app.esperar("!!document.querySelector('[data-aviso-ultimo] [data-resultado]')", 15):
            obs.resultado_desde_aviso = app.js("document.querySelector('[data-aviso-ultimo] [data-resultado]').dataset.resultado")
            _pantalla_llana(app, obs, "radar, resultado del último escaneo")
        app.js("document.querySelector('[data-aviso-ultimo] button').click()")
    # La ficha del primer nicho: dossier y plan a la vista, sin pulsar nada que gaste.
    if app.js("!!document.querySelector('[data-nicho] button')"):
        app.js("document.querySelector('[data-nicho] button').click()")
        obs.ficha_abre = app.esperar("!!document.querySelector('[data-ficha] [data-documento=dossier]') && "
                                     "!!document.querySelector('[data-ficha] [data-documento=plan]')", 15)
        if obs.ficha_abre:
            time.sleep(1)
            _pantalla_llana(app, obs, "ficha del nicho")
        app.js("[...document.querySelectorAll('[data-ficha] button')].find(b => /Radar/.test(b.innerText))?.click()")

    app.ir("Búsqueda", "Semantic", "Search")
    # El campo de la búsqueda, no «main input»: justo después de pulsar puede
    # seguir en pantalla el campo de la vista anterior (sonda del 25-09).
    app.esperar("!!document.querySelector('main [data-campo=busqueda]')", 15)
    app.js("(() => { const i = document.querySelector('main [data-campo=busqueda]');"
           " const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;"
           " set.call(i, 'email notifications'); i.dispatchEvent(new Event('input', {bubbles: true})); })()")
    inicio = time.time()
    app.esperar("document.querySelectorAll('main tbody tr').length > 0 || document.querySelectorAll('main [role=alert]').length > 0", BUSQUEDA_MAX_S)
    obs.busqueda_s = round(time.time() - inicio, 1)
    obs.busqueda_filas = app.js("document.querySelectorAll('main tbody tr').length") or 0
    _pantalla_llana(app, obs, "búsqueda", accion_principal=False)

    app.ir("Fuentes", "Sources")
    app.esperar("document.querySelectorAll('main [data-fuente-fila]').length > 0", 20)
    obs.fuentes_tarjetas = app.js("document.querySelectorAll('main [data-fuente-fila]').length") or 0
    _pantalla_llana(app, obs, "fuentes", accion_principal=False)

    app.ir("Configuración", "Settings")
    obs.config_carga = app.esperar("document.querySelectorAll('main select').length >= 1", 20)
    _pantalla_llana(app, obs, "configuración", accion_principal=False)

    salud = app.js("window.__TAURI_INTERNALS__.invoke('get_app_health')") or {}
    info = salud.get("sidecarInfo") or {}
    obs.huella_compilada, obs.huella_motor, obs.raiz_motor = salud.get("motorBuild"), info.get("build"), info.get("codeRoot")

    obs.excepciones, obs.errores_csp = app.errores()

    plat.cerrar_como_la_x(app.pid)
    obs.cierre_normal = app.esperar_fin(20)
    if not obs.cierre_normal:
        plat.matar_arbol(app.pid)
    app.soltar()
    time.sleep(3)
    obs.huerfanos_tras_cierre = plat.motores()
    return obs


def cerrar_por_ventana_interna(plat: Plataforma, exe: Path, obs: Observado, perfil: Path) -> None:
    """AUD2-027: el cierre que no llega por la X también cierra (Plataforma.cerrar_por_dentro)."""
    proceso = plat.lanzar(exe, perfil)
    fin = time.time() + ARRANQUE_MAX_S + 5
    while not _puerto_ocupado() and time.time() < fin:
        time.sleep(0.25)
    time.sleep(1)
    plat.cerrar_por_dentro(proceso)
    try:
        proceso.wait(timeout=20)
        obs.cierre_ventana_interna = True
    except subprocess.TimeoutExpired:
        plat.matar_arbol(proceso.pid)
    time.sleep(3)
    obs.huerfanos_tras_ventana_interna = plat.motores()


def matar_de_golpe(plat: Plataforma, exe: Path, obs: Observado, perfil: Path) -> None:
    """Como un cuelgue: se mata solo el exe; el motor tiene que terminar solo."""
    proceso = plat.lanzar(exe, perfil)
    fin = time.time() + ARRANQUE_MAX_S + 5
    while not _puerto_ocupado() and time.time() < fin:
        time.sleep(0.25)
    time.sleep(1)
    plat.matar(proceso)
    try:
        proceso.wait(timeout=10)  # recoge el proceso muerto (en Linux quedaría zombi)
    except subprocess.TimeoutExpired:
        pass
    fin = time.time() + FIN_MOTOR_MAX_S
    while time.time() < fin and (_puerto_ocupado() or plat.motores()):
        time.sleep(0.25)
    obs.huerfanos_tras_matar = plat.motores()
    obs.puerto_libre_tras_matar = not _puerto_ocupado()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prueba de humo del ejecutable real de SENTRA")
    plat = plataforma_actual()
    parser.add_argument("--exe", type=Path, default=plat.exe_por_defecto)
    parser.add_argument("--salida", type=Path, default=None)
    args = parser.parse_args(argv)
    # El humo es el único que compara con la base real (en solo lectura): quita la
    # red de seguridad de los tests, también del entorno que hereda el exe.
    from tests._base_real import liberar_para_el_humo

    liberar_para_el_humo()

    if not args.exe.is_file():
        print(f"HUMO FALLA: no existe {args.exe}")
        return 2
    if plat.sentra_abierta() or _puerto_ocupado():
        print("HUMO FALLA: SENTRA está abierta o el puerto 8765 está ocupado; ciérrala y repite")
        return 2

    verdad = verdad_de_la_base()
    perfil = Path(tempfile.mkdtemp(prefix="sentra_humo_webview_"))
    # Sin Google: el exe (y su motor) leen una caché de modelos fresca, copia de la
    # real; el recuento de llm_usage antes y después lo comprueba.
    from core.rutas import CACHE_MODELOS_ENV_VAR, ruta_cache_modelos_gemini

    cache = Path(tempfile.mkdtemp(prefix="sentra_humo_cache_")) / "gemini_models.json"
    preparar_cache_modelos(ruta_cache_modelos_gemini(), cache, ahora=time.time())
    os.environ[CACHE_MODELOS_ENV_VAR] = str(cache)
    uso_antes = contar_uso_gemini()
    antes = plat.huella_perfil_real()
    try:
        with plat.sesion(), plat.vigia() as vigia:
            obs = recorrer(plat, args.exe, perfil)
            cerrar_por_ventana_interna(plat, args.exe, obs, perfil)
            matar_de_golpe(plat, args.exe, obs, perfil)
        obs.primer_plano = vigia.muestras
        obs.perfil_real_antes, obs.perfil_real_despues = antes, plat.huella_perfil_real()
        obs.perfil_aislado_usado = plat.perfil_usado(perfil)
        obs.uso_gemini_nuevo = contar_uso_gemini() - uso_antes
    finally:
        shutil.rmtree(perfil, ignore_errors=True)
        shutil.rmtree(cache.parent, ignore_errors=True)
    fallos = evaluar(obs, verdad, ahora=datetime.now(UTC))
    informe = {"verdad": asdict(verdad), "esperado": asdict(esperado(verdad)), "observado": asdict(obs), "fallos": fallos}
    if args.salida:
        args.salida.write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")
    for fallo in fallos:
        print(f"  ✗ {fallo}")
    print(f"HUMO {'OK' if not fallos else 'FALLA'}: motor {obs.motor_activo_s} s · Radar {obs.radar_nichos}+{obs.radar_descartados} · "
          f"feed {obs.radar_feed} · búsqueda {obs.busqueda_filas} ({obs.busqueda_s} s) · fuentes {obs.fuentes_tarjetas} · "
          f"huérfanos {obs.huerfanos_tras_cierre}/{obs.huerfanos_tras_matar}")
    return 0 if not fallos else 1


if __name__ == "__main__":
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
