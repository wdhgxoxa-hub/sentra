"""
Estimación y confirmación obligatoria antes de escanear (Fase 1, B4)
====================================================================

Decisión de Walter: antes de cada escaneo, llamadas y tokens estimados,
lo gastado hoy y lo que queda; sin confirmar, no se escanea. El motor lo
impone (no solo la interfaz): /api/sources/scan/stream exige el identificador
que devuelve /api/scan/estimate, de un solo uso, que caduca y que vale solo
para el perfil estimado. Si no, 409.

Cómo se estima (todo «estimado»): antes de escanear no se sabe cuántas
piezas pasarán el filtro, así que se da un rango. Llamadas: de 0 a
⌈tope de etiquetas / 20⌉ + 1 (G0) + 2 (confirmaciones de subgrupos) + 1
(abogado), sin pasar del tope por escaneo ni de lo que queda hoy. Tokens:
esas llamadas por la media de cada propósito en llm_usage; sin historial,
25 000 por llamada (lo más alto medido en el etiquetado: 13 000–23 000).
"""

import unittest
from unittest import mock

from core.llm.control import Intento, RegistroEnMemoria, Topes
from core.llm.estimacion import SIN_HISTORIAL_TOKENS, estimar
from tests.test_sidecar_config import ConfigTestCase

PERFIL = {"name": "facturas", "keywords": ["invoice"]}


class TestEstimar(unittest.TestCase):
    def test_sin_historial_usa_el_techo_medido(self):
        e = estimar(Topes(20, 500_000, 40, 1_000_000), uso_hoy=(0, 0), medias={}, tope_etiquetas=300)
        self.assertEqual((e.llamadas_min, e.llamadas_max), (0, 19))
        self.assertEqual((e.tokens_min, e.tokens_max), (0, 19 * SIN_HISTORIAL_TOKENS))
        self.assertFalse(e.con_historial)
        self.assertTrue(e.puede_escanear)

    def test_con_historial_usa_la_media_de_cada_proposito(self):
        e = estimar(Topes(20, 500_000, 40, 1_000_000), uso_hoy=(0, 0),
                    medias={"etiquetado": 10_000, "g0": 5_000, "abogado": 8_000}, tope_etiquetas=300)
        self.assertEqual(e.tokens_max, 15 * 10_000 + 3 * 5_000 + 1 * 8_000)
        self.assertTrue(e.con_historial)

    def test_nunca_pasa_de_los_topes_ni_de_lo_que_queda_hoy(self):
        e = estimar(Topes(10, 100_000, 40, 1_000_000), uso_hoy=(35, 950_000), medias={}, tope_etiquetas=300)
        self.assertEqual((e.llamadas_max, e.tokens_max), (5, 50_000))
        self.assertEqual((e.gastado_hoy, e.queda_hoy), ((35, 950_000), (5, 50_000)))

    def test_sin_nada_que_quede_hoy_no_se_puede_escanear(self):
        e = estimar(Topes(20, 500_000, 40, 1_000_000), uso_hoy=(40, 0), medias={}, tope_etiquetas=300)
        self.assertFalse(e.puede_escanear)
        self.assertEqual(e.llamadas_max, 0)

    def test_el_lote_de_la_estimacion_es_el_del_etiquetado(self):
        from core.judge.labels import BATCH_SIZE, MAX_ITEMS_PER_SCAN
        from core.llm.estimacion import LOTE_DE_ETIQUETADO

        self.assertEqual(LOTE_DE_ETIQUETADO, BATCH_SIZE)
        self.assertEqual(MAX_ITEMS_PER_SCAN, 300)  # los 15 lotes de la estimación sin tope propio

    def test_las_medias_salen_de_lo_que_salio_bien(self):
        registro = RegistroEnMemoria()
        for tokens in (10, 30):
            registro.guardar("r", Intento("m", "etiquetado", "ok", None, tokens, 0, 0))
        registro.guardar("r", Intento("m", "etiquetado", "error", "x", 999, 0, 0))
        registro.guardar("r", Intento("-", "listado_modelos", "ok"))
        self.assertEqual(registro.medias_de_tokens(), {"etiquetado": 20.0})


class TestConfirmacionObligatoria(ConfigTestCase):
    def estimar(self, perfil=PERFIL):
        respuesta = self.client.post("/api/scan/estimate", json={"profile": perfil})
        self.assertEqual(respuesta.status_code, 200, respuesta.text)
        return respuesta.json()

    def escanear(self, confirmacion, perfil=PERFIL):
        cuerpo = {"profile": perfil, "persist": False}
        if confirmacion is not None:
            cuerpo["confirmation"] = confirmacion
        return self.client.post("/api/sources/scan/stream", json=cuerpo)

    def test_la_estimacion_dice_rango_gastado_restante_y_que_es_estimada(self):
        cuerpo = self.estimar()
        self.assertTrue(cuerpo["confirmationId"])
        estimacion = cuerpo["estimate"]
        self.assertEqual(estimacion["calls"], {"min": 0, "max": 19})
        self.assertTrue(estimacion["estimated"])
        self.assertEqual(estimacion["spentToday"], {"calls": 0, "tokens": 0})
        self.assertEqual(estimacion["leftToday"], {"calls": 40, "tokens": 1_000_000})

    def test_la_estimacion_cumple_el_tipo_de_la_interfaz(self):
        # Contrato Python → TS (ts_types.json lo genera el compilador de TypeScript).
        import json
        from pathlib import Path

        tipos = json.loads((Path(__file__).resolve().parents[1] / "ui" / "src-tauri" / "contract"
                            / "ts_types.json").read_text("utf-8"))["interfaces"]
        cuerpo = self.estimar()
        self.assertEqual(set(cuerpo), set(tipos["ScanEstimate"]))
        self.assertEqual(set(cuerpo["estimate"]), set(tipos["ScanEstimateDetail"]))
        self.assertEqual(set(cuerpo["estimate"]["calls"]), set(tipos["EstimateRange"]))
        self.assertEqual(set(cuerpo["estimate"]["spentToday"]), set(tipos["GeminiSpent"]))

    def test_sin_confirmacion_no_se_escanea(self):
        respuesta = self.escanear(None)
        self.assertEqual((respuesta.status_code, respuesta.json()["detail"]["code"]),
                         (409, "scan_confirmation_required"))

    def test_una_confirmacion_solo_vale_una_vez(self):
        from tests.test_sidecar_multiscan import hn_con_una_queja
        from tests.test_sidecar_sources import con_transporte

        confirmacion = self.estimar()["confirmationId"]
        with con_transporte(hn_con_una_queja):  # el escaneo válido corre sin red real
            self.assertEqual(self.escanear(confirmacion).status_code, 200)
        respuesta = self.escanear(confirmacion)
        self.assertEqual((respuesta.status_code, respuesta.json()["detail"]["code"]),
                         (409, "scan_confirmation_used"))

    def test_una_confirmacion_caduca(self):
        from core.orchestration.sidecar import multiscan

        confirmacion = self.estimar()["confirmationId"]
        with mock.patch.object(multiscan, "CONFIRMACION_VALIDA_S", -1.0):
            respuesta = self.escanear(confirmacion)
        self.assertEqual((respuesta.status_code, respuesta.json()["detail"]["code"]),
                         (409, "scan_confirmation_expired"))

    def test_una_confirmacion_es_para_el_perfil_estimado(self):
        confirmacion = self.estimar()["confirmationId"]
        respuesta = self.escanear(confirmacion, perfil={"name": "otro", "keywords": ["otra cosa"]})
        self.assertEqual((respuesta.status_code, respuesta.json()["detail"]["code"]),
                         (409, "scan_confirmation_mismatch"))

    def test_una_confirmacion_inventada_no_vale(self):
        respuesta = self.escanear("no-existe")
        self.assertEqual((respuesta.status_code, respuesta.json()["detail"]["code"]),
                         (409, "scan_confirmation_required"))


if __name__ == "__main__":
    unittest.main()
