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

from tests.humo_exe import Observado, Verdad, esperado, evaluar

AHORA = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def verdad(**cambios: Any) -> Verdad:
    return replace(Verdad(veredictos_ultima=9, evidencia_visible=82, fuentes_catalogo=10,
                          hay_vectores=True), **cambios)


def observado(**cambios: Any) -> Observado:
    """Una app sana: todo cuadra con `verdad()`."""
    return replace(Observado(
        motor_activo_s=4.2, radar_top=6, radar_resto=3, radar_feed=40,
        feed_fechas=["2026-09-23", "2026-05-29"], busqueda_filas=20, fuentes_tarjetas=10,
        config_carga=True, cierre_normal=True, puerto_libre_tras_matar=True,
        url_interfaz="http://tauri.localhost/", cierre_ventana_interna=True,
        huella_compilada="0123456789abcdef", huella_motor="0123456789abcdef",
        raiz_motor="C:/Users/x/AppData/Local/com.sentra.desktop/motor/0123456789abcdef",
        perfil_real_antes="0123abcd", perfil_real_despues="0123abcd", perfil_aislado_usado=True),
        **cambios)


class TestEsperado(unittest.TestCase):
    def test_el_top_se_llena_hasta_seis_y_el_resto_va_debajo(self):
        e = esperado(verdad())
        self.assertEqual((e.top, e.resto, e.feed), (6, 3, 40))

    def test_con_pocos_veredictos_no_se_rellena(self):
        e = esperado(verdad(veredictos_ultima=2, evidencia_visible=5))
        self.assertEqual((e.top, e.resto, e.feed), (2, 0, 5))


class TestEvaluar(unittest.TestCase):
    def test_todo_cuadra_no_hay_fallos(self):
        self.assertEqual(evaluar(observado(), verdad(), ahora=AHORA), [])

    def test_una_vista_vacia_con_datos_en_la_base_es_un_fallo(self):
        fallos = evaluar(observado(radar_top=0, radar_resto=0, radar_feed=0), verdad(), ahora=AHORA)
        self.assertTrue(any("radar" in f.lower() for f in fallos), fallos)

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
        dentro = observado(raiz_motor="F:/reddit_intelligence_radar")
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
