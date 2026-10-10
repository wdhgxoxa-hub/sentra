"""
Propuestas de escaneo en el motor (servidor MCP, paso 3)
========================================================

Claude Desktop deja propuestas (core/mcp); el motor se las da a la ventana
de SENTRA, que las enseña. Walter las descarta o las lanza: al lanzar, el
escaneo lleva el id de la propuesta y el motor la marca como lanzada, ya
con la confirmación de la estimación aceptada. Una propuesta solo se
resuelve una vez.
"""

import json
import unittest
from pathlib import Path
from typing import ClassVar
from unittest import mock

from tests._postgres import ADMIN_DSN, borrar_base_de_prueba, postgres_available
from tests.test_sidecar_config import ConfigTestCase
from tests.test_sidecar_multiscan import PERFIL, confirmacion, eventos, hn_con_una_queja
from tests.test_sidecar_sources import con_transporte

RAIZ = Path(__file__).resolve().parents[1]
TEST_DB = "rir_propuestas_test"
TENANT = "00000000-0000-0000-0000-000000000001"


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestPropuestasEnLaBase(unittest.TestCase):
    dsn: ClassVar[str]

    @classmethod
    def setUpClass(cls):
        import psycopg

        from scripts.migrate import migrate

        borrar_base_de_prueba(TEST_DB)
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        cls.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")
        migrate(cls.dsn, RAIZ / "sql" / "migrations")

    @classmethod
    def tearDownClass(cls):
        borrar_base_de_prueba(TEST_DB)

    def setUp(self):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            conn.execute("DELETE FROM radar.scan_requests")
            conn.execute("DELETE FROM radar.pipeline_runs")

    def proponer(self, nombre="facturas"):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            fila = conn.execute("INSERT INTO radar.scan_requests (tenant_id, profile, reason) "
                                "VALUES (%s, %s::jsonb, 'motivo') RETURNING id::text",
                                (TENANT, json.dumps({**PERFIL, "name": nombre}))).fetchone()
        assert fila is not None
        return fila[0]

    def estado(self, id_):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            return conn.execute("SELECT status, run_id::text FROM radar.scan_requests WHERE id = %s",
                                (id_,)).fetchone()

    def test_las_pendientes_salen_en_orden_con_su_perfil(self):
        from core.propuestas import pendientes

        primera, segunda = self.proponer("uno"), self.proponer("dos")
        vistas = pendientes(self.dsn)
        self.assertEqual([p["id"] for p in vistas], [primera, segunda])
        self.assertEqual(vistas[0]["profile"]["name"], "uno")
        self.assertEqual(vistas[0]["reason"], "motivo")

    def test_descartar_solo_resuelve_una_pendiente(self):
        from core.propuestas import descartar, pendientes

        id_ = self.proponer()
        self.assertTrue(descartar(self.dsn, id_))
        self.assertEqual(self.estado(id_), ("descartada", None))
        self.assertFalse(descartar(self.dsn, id_))
        self.assertFalse(descartar(self.dsn, "no-es-un-uuid"))
        self.assertEqual(pendientes(self.dsn), [])

    def test_lanzada_apunta_a_su_escaneo_y_ya_no_se_puede_descartar(self):
        import psycopg

        from core.propuestas import descartar, marcar_lanzada

        id_ = self.proponer()
        with psycopg.connect(self.dsn) as conn:
            fila = conn.execute("INSERT INTO radar.pipeline_runs (tenant_id, subreddit_name) VALUES (%s, 'x') "
                                "RETURNING id::text", (TENANT,)).fetchone()
        assert fila is not None
        self.assertTrue(marcar_lanzada(self.dsn, id_, fila[0]))
        self.assertEqual(self.estado(id_), ("lanzada", fila[0]))
        self.assertFalse(marcar_lanzada(self.dsn, id_, None))
        self.assertFalse(descartar(self.dsn, id_))


class TestRutasDelMotor(ConfigTestCase):
    """Sin persistencia (estos tests) no hay base: la lista viene vacía."""

    def test_sin_base_no_hay_propuestas_ni_nada_que_descartar(self):
        self.assertEqual(self.client.get("/api/scan-requests").json(), {"requests": []})
        r = self.client.post("/api/scan-requests/00000000-0000-0000-0000-000000000000/discard")
        self.assertEqual(r.status_code, 404)

    def test_con_base_las_rutas_usan_sus_funciones(self):
        from core.orchestration.sidecar import propuestas

        with mock.patch.object(propuestas, "_hay_base", return_value=True), \
                mock.patch("core.propuestas.pendientes", return_value=[{"id": "p1"}]), \
                mock.patch("core.propuestas.descartar", return_value=True) as descartar:
            self.assertEqual(self.client.get("/api/scan-requests").json(), {"requests": [{"id": "p1"}]})
            r = self.client.post("/api/scan-requests/p1/discard")
        self.assertEqual((r.status_code, r.json()), (200, {"discarded": True}))
        self.assertEqual(descartar.call_args.args[1], "p1")


class TestLanzarDesdeUnaPropuesta(ConfigTestCase):
    def escanear(self, **extra):
        return eventos(self.client.post("/api/sources/scan/stream",
                                        json={"profile": PERFIL, "confirmation": confirmacion(self.client),
                                              **extra}))

    def test_el_escaneo_confirmado_marca_su_propuesta_con_la_ejecucion(self):
        from core.orchestration.sidecar import multiscan

        with con_transporte(hn_con_una_queja), \
                mock.patch.object(multiscan, "_abrir_ejecucion", return_value=("run-1", None)), \
                mock.patch.object(multiscan, "_guardar", return_value=None), \
                mock.patch.object(multiscan, "_juzgar", return_value={}), \
                mock.patch.object(multiscan, "_marcar_propuesta") as marcar:
            self.escanear(persist=True, requestId="p1")
        self.assertEqual(marcar.call_args.args[1:], ("p1", "run-1"))

    def test_sin_confirmacion_la_propuesta_sigue_pendiente(self):
        from core.orchestration.sidecar import multiscan

        with mock.patch.object(multiscan, "_marcar_propuesta") as marcar:
            r = self.client.post("/api/sources/scan/stream", json={"profile": PERFIL, "requestId": "p1"})
        self.assertEqual(r.status_code, 409)
        marcar.assert_not_called()

    def test_sin_propuesta_no_se_marca_nada(self):
        from core.orchestration.sidecar import multiscan

        with con_transporte(hn_con_una_queja), mock.patch.object(multiscan, "_marcar_propuesta") as marcar:
            self.escanear(persist=False)
        marcar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
