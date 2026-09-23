"""
Escaneo multifuente desde el sidecar (F2.5)
===========================================

POST /api/sources/scan/stream recibe un perfil de escaneo y emite por SSE el
progreso de cada fuente activa. Al terminar, cada fuente que respondió queda
verificada y, si se persiste, la evidencia se guarda en una ejecución con
data_source='real'. Sin fuentes activas no se escanea nada. Ningún test sale
a la red: el cliente HTTP de las fuentes es un doble con datos inventados.
"""

import json
import time
import unittest
from unittest import mock

import httpx

from tests.test_sidecar_config import ConfigTestCase
from tests.test_sidecar_sources import con_transporte

PERFIL = {"name": "facturas", "keywords": ["invoice"]}


def hn_con_una_queja(_peticion):
    hit = {
        "objectID": "900001", "_tags": ["story", "ask_hn"],
        "created_at_i": int(time.time()) - 86_400,
        "title": "Ask HN: How do you stop exporting invoices by hand?",
        "story_text": "<p>Every month I copy invoices into a spreadsheet. Is there a tool?</p>",
        "author": "autor_inventado", "points": 7, "num_comments": 3,
    }
    return httpx.Response(200, json={"hits": [hit], "nbHits": 1, "page": 0, "nbPages": 1})


def eventos(respuesta):
    return [json.loads(linea[len("data: "):]) for linea in respuesta.text.splitlines()
            if linea.startswith("data: ")]


class TestEscaneoMultifuente(ConfigTestCase):
    def escanear(self, **extra):
        return eventos(self.client.post("/api/sources/scan/stream",
                                        json={"profile": PERFIL, **extra}))

    def test_emite_el_progreso_por_fuente_y_el_resumen(self):
        with con_transporte(hn_con_una_queja):
            recibidos = self.escanear(persist=False)
        tipos = [e["type"] for e in recibidos]
        self.assertEqual(tipos[0], "scan:started")
        self.assertEqual(recibidos[0]["sources"], ["hackernews"])
        self.assertIn("source:started", tipos)
        self.assertIn("source:done", tipos)
        final = recibidos[-1]
        self.assertEqual(final["type"], "scan:done")
        self.assertEqual(final["perSource"]["hackernews"]["status"], "done")
        self.assertEqual(final["perSource"]["hackernews"]["items"], 1)
        self.assertEqual((final["canonical"], final["duplicates"]), (1, 0))
        self.assertFalse(final["persisted"])

    def test_la_fuente_que_respondio_queda_verificada(self):
        with con_transporte(hn_con_una_queja):
            self.escanear(persist=False)
        hn = next(s for s in self.client.get("/api/sources").json()["sources"]
                  if s["source"] == "hackernews")
        self.assertEqual(hn["status"], "verificada")

    def test_la_que_falla_queda_en_error_y_el_escaneo_termina(self):
        with con_transporte(lambda _r: httpx.Response(503)):
            recibidos = self.escanear(persist=False)
        self.assertEqual(recibidos[-1]["type"], "scan:done")
        self.assertEqual(recibidos[-1]["perSource"]["hackernews"]["errorCode"],
                         "source_unavailable")
        hn = next(s for s in self.client.get("/api/sources").json()["sources"]
                  if s["source"] == "hackernews")
        self.assertEqual(hn["status"], "error")

    def test_sin_fuentes_activas_no_escanea(self):
        self.client.post("/api/sources/hackernews/enabled", json={"enabled": False})
        recibidos = self.escanear(persist=False)  # la guardia de red fallaría si saliera
        self.assertEqual([(e["type"], e.get("code")) for e in recibidos],
                         [("error", "no_active_sources")])

    def test_un_perfil_sin_tema_ni_descubrimiento_es_422(self):
        respuesta = self.client.post("/api/sources/scan/stream",
                                     json={"profile": {"name": "vacio"}})
        self.assertEqual(respuesta.status_code, 422)

    def test_persistiendo_informa_de_la_ejecucion(self):
        from core.orchestration.sidecar import multiscan

        with con_transporte(hn_con_una_queja), \
                mock.patch.object(multiscan, "_abrir_ejecucion", return_value=("run-1", None)), \
                mock.patch.object(multiscan, "_guardar", return_value=None) as guardar:
            final = self.escanear(persist=True)[-1]
        self.assertEqual((final["runId"], final["persisted"], final["persistError"]),
                         ("run-1", True, None))
        run_id, resultado = guardar.call_args.args[1:3]
        self.assertEqual(run_id, "run-1")
        self.assertEqual([i.id for i in resultado.fetched], ["hackernews:900001"])

    def test_si_no_se_puede_abrir_la_ejecucion_se_dice_y_no_se_guarda(self):
        from core.orchestration.sidecar import multiscan

        with con_transporte(hn_con_una_queja), \
                mock.patch.object(multiscan, "_abrir_ejecucion",
                                  return_value=(None, "OperationalError: sin base")), \
                mock.patch.object(multiscan, "_guardar") as guardar:
            final = self.escanear(persist=True)[-1]
        self.assertEqual((final["persisted"], final["persistError"]),
                         (False, "OperationalError: sin base"))
        guardar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
