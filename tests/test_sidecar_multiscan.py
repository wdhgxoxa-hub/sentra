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

from tests._ayudas import presente
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


def fin_del_escaneo(recibidos):
    return next(e for e in recibidos if e["type"] == "scan:done")


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
        self.assertIn("hackernews", recibidos[0]["sources"])
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
        from core.sources.catalog import SOURCES

        for clase in SOURCES:
            self.client.post(f"/api/sources/{clase.id}/enabled", json={"enabled": False})
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
                mock.patch.object(multiscan, "_guardar", return_value=None) as guardar, \
                mock.patch.object(multiscan, "_juzgar", return_value={}):
            final = fin_del_escaneo(self.escanear(persist=True))
        self.assertEqual((final["runId"], final["persisted"], final["persistError"]),
                         ("run-1", True, None))
        run_id, resultado = guardar.call_args.args[1:3]
        self.assertEqual(run_id, "run-1")
        self.assertEqual([i.id for i in resultado.fetched], ["hackernews:900001"])

    def test_el_inicio_trae_el_id_para_cancelar_que_es_el_de_la_ejecucion(self):
        from core.orchestration.sidecar import multiscan

        with con_transporte(hn_con_una_queja):
            inicio = self.escanear(persist=False)[0]
        self.assertTrue(inicio["scanId"])
        with con_transporte(hn_con_una_queja), \
                mock.patch.object(multiscan, "_abrir_ejecucion", return_value=("run-9", None)), \
                mock.patch.object(multiscan, "_guardar", return_value=None), \
                mock.patch.object(multiscan, "_juzgar", return_value={}):
            inicio = self.escanear(persist=True)[0]
        self.assertEqual(inicio["scanId"], "run-9")

    def test_cancelar_con_la_ruta_de_siempre_para_las_fuentes_y_lo_dice(self):
        from core.orchestration.sidecar import multiscan

        # Cancelación anticipada: /api/scan/cancel la guarda para ese id.
        self.client.post("/api/scan/cancel", json={"runId": "scan-fijo"})
        with con_transporte(hn_con_una_queja), \
                mock.patch.object(multiscan, "_nuevo_id", return_value="scan-fijo"):
            final = self.escanear(persist=False)[-1]
        self.assertTrue(final["cancelled"])
        self.assertEqual(final["perSource"]["hackernews"]["stopReason"], "cancelled")
        self.assertEqual(final["fetched"], 1, "lo traído antes de cancelar se conserva")
        # Olvidado al terminar: el siguiente escaneo con ese id no nace muerto.
        with con_transporte(hn_con_una_queja), \
                mock.patch.object(multiscan, "_nuevo_id", return_value="scan-fijo"):
            self.assertFalse(self.escanear(persist=False)[-1]["cancelled"])

    def test_cada_fuente_escanea_con_su_presupuesto_propio(self):
        # D-M4: el presupuesto es de cada fuente (YouTube cuenta unidades).
        from core.orchestration.sidecar import multiscan
        from core.sources.budget import SourceBudget
        from core.sources.hackernews import HackerNewsSource

        class HNCorta(HackerNewsSource):
            @classmethod
            def default_budget(cls):
                return SourceBudget(source=cls.id, max_requests=1)

        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return hn_con_una_queja(peticion)

        with con_transporte(manejador), mock.patch.object(multiscan, "SOURCES", (HNCorta,)):
            final = self.escanear(persist=False)[-1]
        self.assertEqual(len(peticiones), 1)
        self.assertEqual(final["perSource"]["hackernews"]["requests"], 1)

    def test_tras_guardar_corre_el_juez_y_emite_su_resumen(self):
        from core.orchestration.sidecar import multiscan

        resumen = {"items": 1, "kept": 1, "clusters": 0, "verdicts": {}}
        with con_transporte(hn_con_una_queja), \
                mock.patch.object(multiscan, "_abrir_ejecucion", return_value=("run-7", None)), \
                mock.patch.object(multiscan, "_guardar", return_value=None), \
                mock.patch.object(multiscan, "_juzgar", return_value=resumen) as juzgar:
            recibidos = self.escanear(persist=True)
        tipos = [e["type"] for e in recibidos]
        self.assertEqual(tipos[-3:], ["scan:done", "judge:started", "judge:done"])
        self.assertEqual((recibidos[-1]["runId"], recibidos[-1]["summary"]), ("run-7", resumen))
        run_id, resultado = juzgar.call_args.args[1:3]
        self.assertEqual((run_id, [i.id for i in resultado.items]), ("run-7", ["hackernews:900001"]))
        # AUD2-001: el tema del perfil llega al juez para que no nombre los nichos.
        self.assertEqual(juzgar.call_args.kwargs.get("tema"), ["invoice"])

    def test_un_fallo_del_juez_no_tumba_el_escaneo(self):
        from core.orchestration.sidecar import multiscan

        with con_transporte(hn_con_una_queja), \
                mock.patch.object(multiscan, "_abrir_ejecucion", return_value=("run-8", None)), \
                mock.patch.object(multiscan, "_guardar", return_value=None), \
                mock.patch.object(multiscan, "_juzgar", side_effect=RuntimeError("inventado")):
            recibidos = self.escanear(persist=True)
        self.assertIn("scan:done", [e["type"] for e in recibidos])
        self.assertEqual((recibidos[-1]["type"], recibidos[-1]["code"]), ("judge:error", "internal_error"))

    def test_mientras_no_hay_eventos_el_flujo_da_senales_de_vida(self):
        # AUD2-025: el juez puede tardar minutos sin emitir nada. El flujo manda
        # un comentario SSE cada KEEPALIVE_S para que la interfaz distinga un
        # escaneo largo y vivo de un motor colgado, sin un límite total.
        from core.orchestration.sidecar import multiscan

        def juez_lento(*_args, **_kwargs):
            time.sleep(0.4)
            return {"clusters": 0}

        with con_transporte(hn_con_una_queja), \
                mock.patch.object(multiscan, "KEEPALIVE_S", 0.05), \
                mock.patch.object(multiscan, "_abrir_ejecucion", return_value=("run-9", None)), \
                mock.patch.object(multiscan, "_guardar", return_value=None), \
                mock.patch.object(multiscan, "_juzgar", side_effect=juez_lento):
            respuesta = self.client.post("/api/sources/scan/stream",
                                         json={"profile": PERFIL, "persist": True})
        self.assertGreaterEqual(respuesta.text.count(": keepalive"), 3)
        self.assertEqual(eventos(respuesta)[-1]["type"], "judge:done")

    def test_sin_guardar_no_hay_juez_y_se_dice(self):
        from core.orchestration.sidecar import multiscan

        with con_transporte(hn_con_una_queja), mock.patch.object(multiscan, "_juzgar") as juzgar:
            recibidos = self.escanear(persist=False)
        juzgar.assert_not_called()
        self.assertEqual(recibidos[-1]["type"], "scan:done")

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


class TestCodigosTraducidos(unittest.TestCase):
    def test_es_y_en_traducen_los_codigos_del_evento_error(self):
        import ast
        import re
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[1]
        arbol = ast.parse((raiz / "core/orchestration/sidecar/multiscan.py").read_text("utf-8"))
        codigos = set()
        for n in ast.walk(arbol):
            if not isinstance(n, ast.Dict):
                continue
            pares = {k.value: v for k, v in zip(n.keys, n.values, strict=True)
                     if isinstance(k, ast.Constant)}
            valor = pares.get("code")
            if "type" in pares and isinstance(valor, ast.Constant):
                codigos.add(valor.value)
        self.assertIn("no_active_sources", codigos)
        for idioma in ("es", "en"):
            fuente = (raiz / "ui/src/i18n" / f"{idioma}.ts").read_text(encoding="utf-8")
            bloque = re.search(r"\n  errors: \{(.*?)\n  \},", fuente, re.DOTALL)
            traducidos = set(re.findall(r"^\s+(\w+):", presente(bloque).group(1), re.MULTILINE))
            with self.subTest(idioma=idioma):
                self.assertEqual(codigos - traducidos, set())


if __name__ == "__main__":
    unittest.main()


class TestJuezSinGemini(ConfigTestCase):
    """AUD-051: sin Gemini el juez corre sin etiquetas, pero no en silencio."""

    def test_sin_clave_queda_en_el_log_y_devuelve_el_motivo(self):
        from core.orchestration.sidecar import multiscan
        from core.orchestration.sidecar.context import SidecarContext

        ctx = SidecarContext(persist_default=False, postgres_dsn=None,
                             env_path=str(self.env_path), started_at=0.0)
        with self.assertLogs("core.orchestration.sidecar.multiscan", "WARNING") as registro:
            proveedor, modelo, motivo = multiscan._proveedor_del_juez(ctx)
        self.assertEqual((proveedor, modelo, motivo), (None, None, "gemini_not_configured"))
        self.assertIn("gemini_not_configured", "\n".join(registro.output))
