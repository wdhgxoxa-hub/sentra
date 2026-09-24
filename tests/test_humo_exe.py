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
        preferencias_antes={"lang": "es", "tema": "system"},
        preferencias_despues={"lang": "es", "tema": "system"}), **cambios)


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

    def test_la_prueba_no_puede_tocar_las_preferencias_del_usuario(self):
        cambiado = observado(preferencias_despues={"lang": "es", "tema": "dark"})
        self.assertTrue(any("preferencias" in f for f in evaluar(cambiado, verdad(), ahora=AHORA)))


if __name__ == "__main__":
    unittest.main()
