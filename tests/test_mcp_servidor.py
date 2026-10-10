"""
Servidor MCP de SENTRA (core/mcp)
=================================

Claude Desktop lee nichos, escaneos y dossiers y puede PROPONER un escaneo,
pero no lanzarlo: la propuesta queda pendiente y solo Walter la lanza desde
la ventana de SENTRA (decisión del 2026-10-09). Aquí se prueba el protocolo
con unos datos falsos, las lecturas y la propuesta contra una base
desechable, y que el proceso real solo escribe JSON-RPC en stdout.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar

from core.mcp.datos import DatoInvalido
from tests._postgres import ADMIN_DSN, borrar_base_de_prueba, postgres_available

RAIZ = Path(__file__).resolve().parents[1]
TEST_DB = "rir_mcp_test"
PERFIL = {"name": "café de especialidad", "topic": "café de especialidad", "keywords": ["café", "tostador"]}


class DatosFalsos:
    def __init__(self) -> None:
        self.propuestas_hechas: list[tuple[dict[str, Any], str]] = []
        self.fallo: Exception | None = None

    def _quiza_falla(self) -> None:
        if self.fallo is not None:
            raise self.fallo

    def estado(self):
        self._quiza_falla()
        return {"escaneos": 3}

    def nichos(self, run_id=None):
        return {"runId": run_id, "verdicts": []}

    def escaneos(self, limite=20):
        return [{"limite": limite}]

    def escaneo(self, run_id):
        return {"run_id": run_id}

    def dossiers(self):
        return [{"id": "a" * 64}]

    def dossier(self, id_):
        return f"# Dossier {id_}\n"

    def propuestas(self):
        return []

    def proponer(self, perfil, motivo):
        self.propuestas_hechas.append((perfil, motivo))
        return {"id": "p1", "estado": "pendiente"}


def pedir(servidor, peticion: dict[str, Any]) -> dict[str, Any]:
    """La respuesta a una petición con id (las notificaciones no tienen)."""
    respuesta = servidor.manejar(peticion)
    assert respuesta is not None
    return respuesta


def llamar(servidor, nombre, argumentos=None, id_=7):
    return pedir(servidor, {"jsonrpc": "2.0", "id": id_, "method": "tools/call",
                            "params": {"name": nombre, "arguments": argumentos or {}}})


def texto(respuesta):
    return respuesta["result"]["content"][0]["text"]


class TestProtocolo(unittest.TestCase):
    def setUp(self):
        from core.mcp.servidor import ServidorMCP

        self.datos = DatosFalsos()
        self.servidor = ServidorMCP(self.datos)

    def test_se_presenta_como_sentra_con_herramientas(self):
        r = pedir(self.servidor, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(r["result"]["serverInfo"]["name"], "sentra")
        self.assertIn("tools", r["result"]["capabilities"])
        self.assertIsNone(self.servidor.manejar({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(pedir(self.servidor, {"jsonrpc": "2.0", "id": 2, "method": "ping"})["result"], {})
        self.assertEqual(pedir(self.servidor, {"jsonrpc": "2.0", "id": 3, "method": "x"})["error"]["code"],
                         -32601)

    def test_ninguna_herramienta_lanza_confirma_ni_descarta(self):
        """Lo único que no es lectura es proponer; lanzar es cosa de la ventana."""
        r = pedir(self.servidor, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        herramientas = {h["name"]: h for h in r["result"]["tools"]}
        self.assertEqual(set(herramientas), {"estado", "nichos", "escaneos", "escaneo", "dossiers", "dossier",
                                             "propuestas", "proponer_escaneo"})
        escriben = {n for n, h in herramientas.items() if not h["annotations"]["readOnlyHint"]}
        self.assertEqual(escriben, {"proponer_escaneo"})
        self.assertIn("NO lo lanza", herramientas["proponer_escaneo"]["description"])

    def test_cada_lectura_llega_a_sus_datos(self):
        self.assertEqual(json.loads(texto(llamar(self.servidor, "estado"))), {"escaneos": 3})
        self.assertEqual(json.loads(texto(llamar(self.servidor, "escaneos", {"limite": 5}))), [{"limite": 5}])
        self.assertEqual(json.loads(texto(llamar(self.servidor, "escaneo", {"run_id": "r"}))), {"run_id": "r"})
        self.assertEqual(json.loads(texto(llamar(self.servidor, "nichos")))["runId"], None)
        self.assertEqual(texto(llamar(self.servidor, "dossier", {"id": "x"})), "# Dossier x\n")

    def test_proponer_deja_la_propuesta_y_dice_que_no_se_ha_gastado_nada(self):
        r = llamar(self.servidor, "proponer_escaneo", {"perfil": PERFIL, "motivo": "pinta bien"})
        self.assertFalse(r["result"]["isError"])
        self.assertEqual(self.datos.propuestas_hechas, [(PERFIL, "pinta bien")])
        self.assertIn("Nada se ha escaneado ni gastado", json.loads(texto(r))["siguiente_paso"])

    def test_un_perfil_que_no_es_objeto_es_un_error_de_la_herramienta(self):
        r = llamar(self.servidor, "proponer_escaneo", {"perfil": "café", "motivo": ""})
        self.assertTrue(r["result"]["isError"])
        self.assertEqual(self.datos.propuestas_hechas, [])

    def test_los_fallos_conocidos_son_errores_de_la_herramienta_no_del_protocolo(self):
        import psycopg

        for fallo, dice in ((DatoInvalido("run_id mal"), "run_id mal"),
                            (psycopg.errors.UndefinedTable(), "migraciones"),
                            (psycopg.OperationalError("x"), "PostgreSQL")):
            with self.subTest(fallo=type(fallo).__name__):
                self.datos.fallo = fallo
                r = llamar(self.servidor, "estado")
                self.assertTrue(r["result"]["isError"])
                self.assertIn(dice, texto(r))

    def test_una_herramienta_desconocida_es_un_error_del_protocolo(self):
        self.assertEqual(llamar(self.servidor, "lanzar_escaneo")["error"]["code"], -32602)


class TestPrivacidadDelRadar(unittest.TestCase):
    def test_el_radar_del_mcp_oculta_los_identificadores_como_la_interfaz(self):
        from core.orchestration.sidecar.judge import radar_para_mostrar

        leido = {"run_id": None, "verdicts": [{"cluster_key": "bluesky:did:plc:abc", "corroboration": {},
                                               "evidence": [{"excerpt": "gracias @martinhowitt por esto"}]}],
                 "rest": []}
        visto = radar_para_mostrar(leido)
        self.assertNotIn("clusterKey", visto["verdicts"][0])
        self.assertEqual(visto["verdicts"][0]["evidence"][0]["excerpt"], "gracias [usuario] por esto")


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestDatosContraUnaBase(unittest.TestCase):
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

        from core.mcp.datos import DatosSentra

        with psycopg.connect(self.dsn) as conn:
            conn.execute("DELETE FROM radar.scan_requests")
        self.carpeta = Path(tempfile.mkdtemp(prefix="mcp_docs_"))
        self.addCleanup(shutil.rmtree, self.carpeta, True)
        self.datos = DatosSentra(self.dsn, documentos=self.carpeta)

    def test_una_propuesta_valida_queda_pendiente(self):
        hecho = self.datos.proponer(PERFIL, "el café sale en muchas quejas")
        self.assertEqual(hecho["estado"], "pendiente")
        [pendiente] = self.datos.propuestas()
        self.assertEqual(pendiente["id"], hecho["id"])
        self.assertEqual(pendiente["perfil"]["keywords"], ["café", "tostador"])
        self.assertEqual(pendiente["motivo"], "el café sale en muchas quejas")
        self.assertEqual(self.datos.estado()["propuestas_pendientes"], 1)

    def test_un_perfil_que_el_motor_rechazaria_no_se_guarda(self):
        for perfil in ({"name": "sin tema"}, {"keywords": ["x"]},
                       {"name": "x", "keywords": ["x"], "discovery": True}):
            with self.subTest(perfil=perfil), self.assertRaises(DatoInvalido):
                self.datos.proponer(perfil, "")
        with self.assertRaises(DatoInvalido):
            self.datos.proponer(PERFIL, "x" * 501)
        self.assertEqual(self.datos.propuestas(), [])

    def test_sin_escaneos_las_lecturas_vienen_vacias(self):
        self.assertEqual(self.datos.escaneos(), [])
        self.assertEqual(self.datos.nichos()["verdicts"], [])
        self.assertEqual(self.datos.estado()["escaneos"], 0)
        self.assertEqual(self.datos.estado()["migraciones_pendientes"], [])
        with self.assertRaises(DatoInvalido):
            self.datos.escaneo("no-es-un-uuid")
        with self.assertRaises(DatoInvalido):
            self.datos.escaneo("00000000-0000-0000-0000-000000000000")
        with self.assertRaises(DatoInvalido):
            self.datos.nichos("'; DROP TABLE x; --")

    def test_un_escaneo_guardado_sale_con_sus_fuentes(self):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            fila = conn.execute(
                "INSERT INTO radar.pipeline_runs (tenant_id, subreddit_name) VALUES "
                "('00000000-0000-0000-0000-000000000001', 'café') RETURNING id::text").fetchone()
            assert fila is not None
            run_id = fila[0]
            conn.execute("INSERT INTO radar.run_source_outcomes (tenant_id, run_id, source, status, items) "
                         "VALUES ('00000000-0000-0000-0000-000000000001', %s, 'hackernews', 'done', 12)",
                         (run_id,))
        self.addCleanup(self._borrar_escaneos)
        [resumen] = self.datos.escaneos()
        self.assertEqual((resumen["run_id"], resumen["name"]), (run_id, "café"))
        detalle = self.datos.escaneo(run_id)
        self.assertEqual([(f["fuente"], f["piezas"]) for f in detalle["fuentes"]], [("hackernews", 12)])

    def _borrar_escaneos(self):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            conn.execute("DELETE FROM radar.pipeline_runs")

    def test_los_dossiers_guardados_se_leen_en_markdown(self):
        from core.documents.almacen import AlmacenDeDocumentos
        from core.documents.model import Block, DocumentModel, Section

        documento = DocumentModel(language="es", kind="dossier", title="Café de especialidad", data_source="real",
                                  cover=(), sections=(Section(id="s", title="Resumen",
                                                              blocks=(Block(kind="paragraph", text="Hola."),)),))
        AlmacenDeDocumentos(self.carpeta).guardar(("v1", "dossier", "es", "m", False), documento)
        [fila] = self.datos.dossiers()
        self.assertEqual((fila["title"], fila["kind"], fila["verdict_id"]), ("Café de especialidad", "dossier", "v1"))
        self.assertIn("# Café de especialidad", self.datos.dossier(fila["id"]))
        for malo in ("../../etc/passwd", "0" * 64):
            with self.subTest(id=malo), self.assertRaises(DatoInvalido):
                self.datos.dossier(malo)


class TestProcesoReal(unittest.TestCase):
    def test_stdout_solo_lleva_respuestas_json_rpc(self):
        """Claude Desktop lee stdout como protocolo: un aviso impreso ahí lo rompe."""
        entrada = "\n".join(json.dumps(p) for p in (
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )) + "\nesto no es json\n"
        r = subprocess.run([sys.executable, "-m", "core.mcp.servidor"], input=entrada, cwd=RAIZ,
                           capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        respuestas = [json.loads(linea) for linea in r.stdout.splitlines()]
        self.assertEqual([x.get("id") for x in respuestas], [1, 2, None])
        self.assertEqual(respuestas[2]["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()
