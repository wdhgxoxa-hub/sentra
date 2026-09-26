"""
Lógica de la prueba de humo del ejecutable (AUD2-004)
====================================================

La prueba de humo (`python -m tests.humo_exe`) lanza el ejecutable real y
compara lo que pinta cada vista con la base leída en solo lectura. Aquí se
prueba, sin lanzar nada, la parte que decide: qué se espera según la base y
qué fallos hay en lo observado. Un fallo de esta lógica haría que el humo
pasara en verde con la app rota, que es justo lo que no puede volver a pasar.
"""

import unittest
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from tests.humo_exe import RAIZ, Observado, Verdad, esperado, evaluar

AHORA = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def verdad(**cambios: Any) -> Verdad:
    return replace(Verdad(veredictos_ultima=9, evidencia_visible=82, fuentes_catalogo=10,
                          hay_vectores=True, nichos_ultima=2, aviso_ultimo=True), **cambios)


def observado(**cambios: Any) -> Observado:
    """Una app sana: todo cuadra con `verdad()`."""
    return replace(Observado(
        motor_activo_s=4.2, radar_nichos=2, radar_descartados=7, radar_feed=40,
        resultado_desde_aviso="cero_nichos", ficha_abre=True,
        feed_fechas=["2026-09-23", "2026-05-29"], busqueda_filas=20, fuentes_tarjetas=10,
        config_carga=True, cierre_normal=True, puerto_libre_tras_matar=True,
        url_interfaz="http://tauri.localhost/", cierre_ventana_interna=True,
        huella_compilada="0123456789abcdef", huella_motor="0123456789abcdef",
        raiz_motor="C:/Users/x/AppData/Local/com.sentra.desktop/motor/0123456789abcdef",
        perfil_real_antes="0123abcd", perfil_real_despues="0123abcd", perfil_aislado_usado=True,
        pantalla_inicial="nuevo", acciones_principales={"nuevo": 1}, jerga={"nuevo": []},
        asistente_paso2=True),
        **cambios)


class TestEsperado(unittest.TestCase):
    def test_el_radar_ensena_los_nichos_y_aparte_los_descartados(self):
        """Fase 2: todos los veredictos de la ejecución con nichos; los nichos
        (CONSTRUIR, INVESTIGAR MÁS) a la vista y los descartados plegados."""
        e = esperado(verdad())
        self.assertEqual((e.nichos, e.descartados, e.feed), (2, 7, 40))

    def test_el_feed_recorta_a_40(self):
        e = esperado(verdad(veredictos_ultima=2, nichos_ultima=0, evidencia_visible=5))
        self.assertEqual((e.nichos, e.descartados, e.feed), (0, 2, 5))


class TestEvaluar(unittest.TestCase):
    def test_todo_cuadra_no_hay_fallos(self):
        self.assertEqual(evaluar(observado(), verdad(), ahora=AHORA), [])

    def test_una_vista_vacia_con_datos_en_la_base_es_un_fallo(self):
        fallos = evaluar(observado(radar_nichos=0, radar_descartados=0, radar_feed=0), verdad(), ahora=AHORA)
        self.assertTrue(any("radar" in f.lower() for f in fallos), fallos)

    def test_el_aviso_del_radar_tiene_que_llevar_al_resultado_del_ultimo_escaneo(self):
        fallos = evaluar(observado(resultado_desde_aviso=None), verdad(), ahora=AHORA)
        self.assertTrue(any("aviso" in f for f in fallos), fallos)
        self.assertEqual(evaluar(observado(resultado_desde_aviso=None), verdad(aviso_ultimo=False),
                                 ahora=AHORA), [], "sin aviso no hay nada que abrir")

    def test_con_nichos_la_ficha_tiene_que_abrirse(self):
        fallos = evaluar(observado(ficha_abre=False), verdad(), ahora=AHORA)
        self.assertTrue(any("ficha" in f for f in fallos), fallos)
        self.assertEqual(evaluar(observado(ficha_abre=False, radar_nichos=0),
                                 verdad(nichos_ultima=0, veredictos_ultima=7), ahora=AHORA), [])

    def test_la_app_tiene_que_arrancar_en_nuevo_escaneo(self):
        """Fase 2: «Nuevo escaneo» es la pantalla principal."""
        fallos = evaluar(observado(pantalla_inicial="radar"), verdad(), ahora=AHORA)
        self.assertTrue(any("nuevo escaneo" in f.lower() for f in fallos), fallos)

    def test_cada_pantalla_nueva_tiene_una_sola_accion_principal(self):
        for n in (0, 2):
            fallos = evaluar(observado(acciones_principales={"nuevo": n}), verdad(), ahora=AHORA)
            self.assertTrue(any("acción principal" in f for f in fallos), (n, fallos))

    def test_la_jerga_visible_es_un_fallo(self):
        fallos = evaluar(observado(jerga={"nuevo": ["tokens", "G0-G9"]}), verdad(), ahora=AHORA)
        self.assertTrue(any("tokens" in f and "nuevo" in f for f in fallos), fallos)

    def test_un_identificador_de_autor_visible_es_un_fallo(self):
        """R9 (Fase 3): ni DID, ni at://, ni @usuario en ninguna pantalla, tampoco
        en los «Ver detalle» ni en el texto ajeno."""
        fallos = evaluar(observado(identificadores={"radar": ["did:plc:fxxq6d7qa7vggtoc7gsn6m2w"]}), verdad(), ahora=AHORA)
        self.assertTrue(any("did:plc:" in f and "radar" in f and "R9" in f for f in fallos), fallos)

    def test_identificadores_visibles_fuera_de_la_direccion_del_original(self):
        """La dirección de Bluesky lleva el DID (R5 frente a R9, decisión de Walter
        pendiente): no cuenta; el mismo DID en un nombre o una cita, sí."""
        from tests.humo_exe import identificadores_visibles

        url = "Original: https://bsky.app/profile/did:plc:z2gdgxz2um3eq47a2ebsz3wz/post/3mwc"
        self.assertEqual(identificadores_visibles(url), [])
        self.assertEqual(len(identificadores_visibles("Grupo bluesky:did:plc:abc12 · gracias @ana")), 2)

    def test_un_texto_largo_que_desborda_la_pantalla_es_un_fallo(self):
        """Fase 3: un texto ajeno largo sin espacios (una dirección, una clave) se
        parte; si empuja la pantalla hacia la derecha, falla."""
        fallos = evaluar(observado(desborde={"radar, resultado del último escaneo": 741}), verdad(), ahora=AHORA)
        self.assertTrue(any("741" in f and "resultado" in f and "derecha" in f for f in fallos), fallos)
        self.assertFalse(evaluar(observado(desborde={"radar": 0}), verdad(), ahora=AHORA))

    def test_el_humo_lanza_la_app_en_modo_discreto(self):
        """Walter (Fase 3): el humo no puede robar el foco ni verse. La ventana nace
        oculta y solo se muestra fuera del modo discreto."""
        import json

        from tests.humo_exe import entorno

        self.assertEqual(entorno(None)["SENTRA_VENTANA_DISCRETA"], "1")
        self.assertEqual(entorno(None, cdp=True)["SENTRA_VENTANA_DISCRETA"], "1")
        conf = json.loads((RAIZ / "ui" / "src-tauri" / "tauri.conf.json").read_text("utf-8"))
        self.assertIs(conf["app"]["windows"][0]["visible"], False)
        # tao activaba la ventana oculta al crearla (focus true por defecto): el
        # vigía de la compuerta la vio en primer plano 154 y 23 muestras.
        self.assertIs(conf["app"]["windows"][0]["focus"], False)

    def test_el_vigia_reconoce_a_sentra_por_su_ejecutable(self):
        from unittest import mock

        from tests.humo_exe import VigiaDePrimerPlano as V

        for ruta, esperado_ in ((r"F:\repo\ui\src-tauri\target\release\sentra.exe", True),
                                (r"C:\Windows\explorer.exe", False), ("", False),
                                (r"C:\x\nosentra.exe", False)):
            with mock.patch.object(V, "imagen_del_primer_plano", return_value=ruta):
                self.assertIs(V.es_de_sentra(), esperado_, ruta)

    def test_una_ventana_de_sentra_en_primer_plano_es_un_fallo(self):
        fallos = evaluar(observado(primer_plano=23), verdad(), ahora=AHORA)
        self.assertTrue(any("primer plano" in f and "23" in f for f in fallos), fallos)
        self.assertFalse(evaluar(observado(primer_plano=0), verdad(), ahora=AHORA))

    def test_el_humo_mira_la_app_con_su_ancho_minimo(self):
        """Oculta, la ventana mide lo de la configuración (1440); visible, lo que
        decida el gestor de ventanas (822 con GlazeWM). El humo fija la vista al
        mínimo que permite la app: mismo resultado siempre y lo más estricto."""
        import json

        from tests.humo_exe import VISTA_DEL_HUMO

        ventana = json.loads((RAIZ / "ui" / "src-tauri" / "tauri.conf.json").read_text("utf-8"))["app"]["windows"][0]
        self.assertEqual(VISTA_DEL_HUMO, (ventana["minWidth"], ventana["minHeight"]))

    def test_el_asistente_que_no_pasa_al_paso_2_es_un_fallo(self):
        fallos = evaluar(observado(asistente_paso2=False), verdad(), ahora=AHORA)
        self.assertTrue(any("asistente" in f for f in fallos), fallos)

    def test_el_motor_que_no_arranca_es_un_fallo(self):
        self.assertTrue(evaluar(observado(motor_activo_s=None), verdad(), ahora=AHORA))

    def test_evidencia_con_fecha_futura_o_sin_fuente_es_un_fallo(self):
        self.assertTrue(evaluar(observado(feed_fechas=["2099-12-31"]), verdad(), ahora=AHORA))
        self.assertTrue(evaluar(observado(feed_fuente_desconocida=3), verdad(), ahora=AHORA))

    def test_la_busqueda_sin_filas_teniendo_vectores_es_un_fallo(self):
        self.assertTrue(evaluar(observado(busqueda_filas=0), verdad(), ahora=AHORA))
        self.assertEqual(evaluar(observado(busqueda_filas=0), verdad(hay_vectores=False), ahora=AHORA), [])

    def test_excepciones_csp_y_huerfanos_son_fallos(self):
        for cambio in ({"excepciones": ["TypeError"]}, {"errores_csp": 2},
                       {"huerfanos_tras_cierre": 1}, {"huerfanos_tras_matar": 1},
                       {"puerto_libre_tras_matar": False}, {"cierre_normal": False}):
            with self.subTest(cambio):
                self.assertTrue(evaluar(observado(**cambio), verdad(), ahora=AHORA))

    def test_el_motor_tiene_que_ser_el_de_esta_interfaz_y_no_el_del_repo(self):
        self.assertTrue(evaluar(observado(huella_motor="ffffffffffffffff"), verdad(), ahora=AHORA))
        self.assertTrue(evaluar(observado(huella_motor=None), verdad(), ahora=AHORA))
        # La raíz de este repo, esté donde esté el clon (F1: en una instalación limpia
        # en otra carpeta, una ruta fija de F: ya no era «el repositorio»).
        dentro = observado(raiz_motor=str(RAIZ))
        self.assertTrue(any("repositorio" in f for f in evaluar(dentro, verdad(), ahora=AHORA)))

    def test_un_exe_sin_la_interfaz_embebida_es_un_fallo(self):
        # `cargo build --release` sin la feature custom-protocol de Tauri deja un
        # exe que abre el servidor de desarrollo: la ventana queda vacía.
        for url in ("http://localhost:5173/", None):
            with self.subTest(url):
                fallos = evaluar(observado(url_interfaz=url), verdad(), ahora=AHORA)
                self.assertTrue(any("interfaz embebida" in f for f in fallos), fallos)

    def test_un_cierre_por_la_ventana_interna_que_cuelga_la_app_es_un_fallo(self):
        # AUD2-027: WM_CLOSE a la «Tao Thread Event Target» (visible a propósito
        # en tao) la destruía y el proceso quedaba vivo sin ventana al cerrar.
        fallos = evaluar(observado(cierre_ventana_interna=False), verdad(), ahora=AHORA)
        self.assertTrue(any("ventana interna" in f for f in fallos), fallos)
        fallos = evaluar(observado(huerfanos_tras_ventana_interna=2), verdad(), ahora=AHORA)
        self.assertTrue(any("ventana interna" in f for f in fallos), fallos)

    def test_la_prueba_no_puede_tocar_el_perfil_del_usuario(self):
        # Perfil de WebView aislado (pedido por el usuario): el Local Storage real
        # (idioma, tema) no puede cambiar ni un byte.
        cambiado = observado(perfil_real_despues="ffff0000")
        self.assertTrue(any("perfil real" in f for f in evaluar(cambiado, verdad(), ahora=AHORA)))

    def test_si_la_app_no_usa_el_perfil_aislado_es_un_fallo(self):
        # Si WEBVIEW2_USER_DATA_FOLDER dejara de mandar, la app volvería al perfil real.
        fallos = evaluar(observado(perfil_aislado_usado=False), verdad(), ahora=AHORA)
        self.assertTrue(any("perfil aislado" in f for f in fallos), fallos)


class TestSinGemini(unittest.TestCase):
    """El humo es una prueba automática: no llama a Google ni escribe en el
    llm_usage real, aunque haya caducado la lista de modelos (decisión de Walter)."""

    def test_una_fila_nueva_en_llm_usage_es_un_fallo(self):
        fallos = evaluar(observado(uso_gemini_nuevo=1), verdad(), ahora=AHORA)
        self.assertTrue(any("Gemini" in f for f in fallos), fallos)

    def test_la_cache_del_humo_es_la_real_con_la_hora_de_ahora(self):
        import json
        import shutil
        import tempfile
        from pathlib import Path

        from tests.humo_exe import preparar_cache_modelos

        carpeta = Path(tempfile.mkdtemp(prefix="humo_cache_"))
        self.addCleanup(shutil.rmtree, carpeta, True)
        origen, destino = carpeta / "real.json", carpeta / "humo" / "modelos.json"
        modelos = [{"id": "gemini-x", "display_name": "X", "input_token_limit": 1, "output_token_limit": 2}]
        origen.write_text(json.dumps({"huella": {"listed_at": 1.0, "models": modelos}}), "utf-8")
        self.assertEqual(preparar_cache_modelos(origen, destino, ahora=5000.0), 1)
        self.assertEqual(json.loads(destino.read_text("utf-8")),
                         {"huella": {"listed_at": 5000.0, "models": modelos}})
        # Sin caché real queda una vacía: si el motor llamara a Google, el
        # recuento de llm_usage lo delataría.
        self.assertEqual(preparar_cache_modelos(carpeta / "no_existe.json", destino, ahora=1.0), 0)
        self.assertEqual(json.loads(destino.read_text("utf-8")), {})


class TestEsperas(unittest.TestCase):
    def test_la_busqueda_se_espera_al_menos_lo_que_la_espera_la_app(self):
        # Falso rojo tras una compilación: el humo se rendía a los 30 s y la app
        # espera 60 (la primera búsqueda carga e5 en frío).
        import re

        from tests.humo_exe import BUSQUEDA_MAX_S, RAIZ

        rust = (RAIZ / "ui" / "src-tauri" / "src" / "commands" / "engine.rs").read_text(encoding="utf-8")
        encontrado = re.search(r"SEARCH_TIMEOUT: Duration = Duration::from_secs\((\d+)\)", rust)
        assert encontrado is not None
        self.assertGreater(BUSQUEDA_MAX_S, int(encontrado.group(1)))


class TestUrlDeLaInterfaz(unittest.TestCase):
    """La URL se lee cuando WebView2 ya ha navegado (falso rojo del 2026-09-24:
    el humo leyó `about:blank` nada más conectarse y la app sí cargó)."""

    def _leer(self, *urls: str | None):
        pendientes = list(urls)
        return lambda: pendientes.pop(0) if len(pendientes) > 1 else pendientes[0]

    def _reloj(self):
        ahora = [0.0]

        def dormir(s: float) -> None:
            ahora[0] += s

        return (lambda: ahora[0]), dormir

    def test_espera_a_que_la_pagina_deje_de_ser_about_blank(self):
        from tests.humo_exe import url_de_la_interfaz

        reloj, dormir = self._reloj()
        url = url_de_la_interfaz(self._leer("about:blank", None, "http://tauri.localhost/"),
                                 limite=10.0, reloj=reloj, dormir=dormir)
        self.assertEqual(url, "http://tauri.localhost/")

    def test_un_exe_que_se_queda_en_blanco_sigue_siendo_un_fallo(self):
        from tests.humo_exe import url_de_la_interfaz

        reloj, dormir = self._reloj()
        url = url_de_la_interfaz(self._leer("about:blank"), limite=10.0, reloj=reloj, dormir=dormir)
        self.assertEqual(url, "about:blank")
        self.assertGreaterEqual(reloj(), 10.0)
        fallos = evaluar(observado(url_interfaz=url), verdad(), ahora=AHORA)
        self.assertTrue(any("interfaz embebida" in f for f in fallos), fallos)

    def test_el_servidor_de_desarrollo_se_devuelve_sin_esperar(self):
        # El exe de `cargo build --release` navega a localhost:5173: no hay que
        # esperar, y evaluar() lo marca.
        from tests.humo_exe import url_de_la_interfaz

        reloj, dormir = self._reloj()
        url = url_de_la_interfaz(self._leer("http://localhost:5173/"), limite=10.0,
                                 reloj=reloj, dormir=dormir)
        self.assertEqual((url, reloj()), ("http://localhost:5173/", 0.0))


class TestLectorCdp(unittest.TestCase):
    def test_un_minuto_sin_mensajes_no_mata_al_lector(self):
        # AUD2-026: con la app en reposo pasaba más de un minuto sin mensajes
        # CDP; recv() lanzaba timeout, el hilo lector moría y toda respuesta
        # posterior se perdía (heap y nodos a 0 en la medida larga).
        import websocket

        from tests.humo_exe import _Cdp

        class WsFalso:
            def __init__(self):
                self.pasos = [websocket.WebSocketTimeoutException("silencio"),
                              '{"id": 7, "result": {}}', ConnectionError("cerrada")]

            def recv(self):
                paso = self.pasos.pop(0)
                if isinstance(paso, Exception):
                    raise paso
                return paso

        cdp = _Cdp.__new__(_Cdp)
        cdp.ws = WsFalso()  # type: ignore[assignment]  # doble: solo recv()
        cdp._respuestas, cdp.excepciones, cdp.errores_csp = {}, [], 0
        cdp._leer()
        self.assertIn(7, cdp._respuestas)


if __name__ == "__main__":
    unittest.main()


class TestEsperasQueMidenBien(unittest.TestCase):
    """Un nodo del DOM llega por CDP como {} y en Python {} es falso: una espera
    sobre `document.querySelector(...)` sin `!!` nunca se cumple y agota su
    tiempo en silencio (la búsqueda esperaba 15 s siempre; el asistente de la
    Fase 2 parecía no pasar al paso 2). Toda espera sobre un nodo lo convierte
    antes en booleano."""

    def test_ninguna_espera_devuelve_un_nodo(self):
        import re

        fuente = (RAIZ / "tests" / "humo_exe.py").read_text("utf-8")
        esperas = re.findall(r"""\.esperar\(\s*(?:f?"|f?')(.*?)(?:"|')\s*,""", fuente)
        self.assertTrue(esperas)
        for expresion in esperas:
            with self.subTest(expresion=expresion):
                if "querySelector(" in expresion:
                    self.assertTrue(expresion.lstrip().startswith("!!") or ".length" in expresion
                                    or "==" in expresion, expresion)

