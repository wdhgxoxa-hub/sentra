"""
Migraciones pendientes: aviso, no un 500 (incidente del 2026-09-23)
===================================================================

La base real estaba en la migración 8 y la rama ya necesitaba la 009: la
sección Fuentes devolvía 500 con «no existe la relación sources_state».
Ahora el motor responde 503 con el código `migrations_pending` y la lista
de lo que falta, y el escaneo multifuente lo emite como evento de error.
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import psycopg
from fastapi.testclient import TestClient

from tests._ayudas import presente
from tests._sin_red import prohibir_red_real


class EstadoSinTabla:
    """sources_state en una base sin la migración 009."""

    def get(self, source):
        raise psycopg.errors.UndefinedTable('no existe la relación «sources_state»')

    def record_probe(self, source, result):  # pragma: no cover
        raise psycopg.errors.UndefinedTable("sources_state")

    def set_disabled(self, source, disabled):
        raise psycopg.errors.UndefinedTable("sources_state")

    def reset(self, source):  # pragma: no cover
        raise psycopg.errors.UndefinedTable("sources_state")


class TestMigracionesPendientes(unittest.TestCase):
    def setUp(self):
        prohibir_red_real(self)
        from core.orchestration import sidecar_server

        tmp = tempfile.mkdtemp(prefix="rir_mig_")
        self.addCleanup(shutil.rmtree, tmp, True)
        parches = [
            mock.patch.object(sidecar_server, "_estado_de_fuentes",
                              return_value=EstadoSinTabla()),
            mock.patch("core.orchestration.sidecar.migrations.pending_migration_names",
                       return_value=["009_evidence_items"]),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)
        app = sidecar_server.create_app(
            insecure_dev=True, persist_default=False, env_path=os.path.join(tmp, ".env"))
        self.client = TestClient(app)

    def test_las_fuentes_responden_503_con_el_codigo_y_lo_que_falta(self):
        respuesta = self.client.get("/api/sources")
        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(respuesta.json()["detail"]["code"], "migrations_pending")
        self.assertIn("009_evidence_items", respuesta.json()["detail"]["detail"])

    def test_tambien_al_encender_una_fuente(self):
        respuesta = self.client.post("/api/sources/hackernews/enabled", json={"enabled": False})
        self.assertEqual(respuesta.json()["detail"]["code"], "migrations_pending")

    def test_el_escaneo_multifuente_lo_emite_como_evento(self):
        respuesta = self.client.post("/api/sources/scan/stream",
                                     json={"profile": {"name": "x", "keywords": ["y"]}})
        eventos = [json.loads(linea[6:]) for linea in respuesta.text.splitlines()
                   if linea.startswith("data: ")]
        self.assertEqual([(e["type"], e["code"]) for e in eventos],
                         [("error", "migrations_pending")])
        self.assertIn("009_evidence_items", eventos[0]["message"])


class TestTraduccion(unittest.TestCase):
    def test_es_y_en_traducen_migrations_pending(self):
        import re
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[1] / "ui" / "src" / "i18n"
        for idioma in ("es", "en"):
            fuente = (raiz / f"{idioma}.ts").read_text(encoding="utf-8")
            bloque = re.search(r"\n  errors: \{(.*?)\n  \},", fuente, re.DOTALL)
            with self.subTest(idioma=idioma):
                self.assertRegex(presente(bloque).group(1), r"\n\s+migrations_pending:")


if __name__ == "__main__":
    unittest.main()
