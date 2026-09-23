"""
Identidad estable de cada oportunidad (AUD-019, decisión D-G)
=============================================================

`cluster_key` se calcula con la intención y las palabras clave: en cuanto un
problema ganaba una palabra entre escaneos, cambiaba de clave y perdía su
historial y su validación. Ahora cada oportunidad tiene un UUID que hereda
la lectura nueva si comparte al menos MEMBER_JACCARD_MIN de sus señales o,
si no, KEYWORD_JACCARD_MIN de sus palabras clave. Si no, UUID nuevo. Dos
problemas nunca heredan el mismo UUID.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from core.storage.identity import (
    KEYWORD_JACCARD_MIN,
    MEMBER_JACCARD_MIN,
    Candidato,
    Previo,
    asignar_identidades,
    jaccard,
)

RAIZ = Path(__file__).resolve().parents[1]


class TestAsignacion(unittest.TestCase):

    def test_los_umbrales_son_constantes_con_nombre(self):
        self.assertEqual(MEMBER_JACCARD_MIN, 0.5)
        self.assertEqual(KEYWORD_JACCARD_MIN, 0.6)

    def test_jaccard(self):
        self.assertEqual(jaccard({"a", "b"}, {"b", "c"}), 1 / 3)
        self.assertEqual(jaccard(set(), set()), 0.0)

    def test_un_problema_que_gana_palabras_conserva_su_uuid_por_sus_senales(self):
        previos = [Previo("uuid-a", {"p1", "p2", "p3"}, {"invoice", "manual"})]
        nuevos = [Candidato("complaint:export|invoice|manual", {"p1", "p2", "p3", "p4"},
                            {"invoice", "manual", "export", "reconcile", "csv"})]
        self.assertEqual(asignar_identidades(nuevos, previos),
                         {"complaint:export|invoice|manual": "uuid-a"})

    def test_sin_senales_comunes_hereda_por_palabras_clave(self):
        previos = [Previo("uuid-a", {"p1"}, {"invoice", "manual", "export"})]
        nuevos = [Candidato("k", {"p9"}, {"invoice", "manual", "export", "csv"})]
        self.assertEqual(asignar_identidades(nuevos, previos), {"k": "uuid-a"})

    def test_por_debajo_de_los_dos_umbrales_es_una_oportunidad_nueva(self):
        previos = [Previo("uuid-a", {"p1", "p2", "p3"}, {"invoice", "manual"})]
        nuevos = [Candidato("k", {"p3", "p8", "p9"}, {"invoice", "onboarding", "sso"})]
        self.assertEqual(asignar_identidades(nuevos, previos), {"k": None})

    def test_dos_problemas_distintos_no_heredan_el_mismo_uuid(self):
        previos = [Previo("uuid-a", {"p1", "p2"}, {"invoice", "manual"})]
        nuevos = [
            Candidato("uno", {"p1", "p2"}, {"invoice", "manual"}),
            Candidato("otro", {"p1", "p2", "p5"}, {"invoice", "manual"}),
        ]
        asignacion = asignar_identidades(nuevos, previos)
        self.assertEqual(asignacion["uno"], "uuid-a")  # el mejor emparejado
        self.assertIsNone(asignacion["otro"])

    def test_las_senales_mandan_sobre_las_palabras(self):
        previos = [
            Previo("por-palabras", {"x1"}, {"invoice", "manual"}),
            Previo("por-senales", {"p1", "p2"}, {"billing"}),
        ]
        nuevos = [Candidato("k", {"p1", "p2"}, {"invoice", "manual"})]
        self.assertEqual(asignar_identidades(nuevos, previos), {"k": "por-senales"})


ADMIN_DSN = os.environ.get(
    "RIR_PG_ADMIN_DSN", "host=localhost port=5432 user=postgres dbname=postgres"
)
TEST_DB = "rir_identity_test"


def _postgres_available() -> bool:
    try:
        import psycopg

        with psycopg.connect(ADMIN_DSN, connect_timeout=3):
            return True
    except Exception:  # noqa: BLE001 - sondeo de disponibilidad del servidor de pruebas
        return False


def estado(posts):
    """Estado del grafo con una cosecha de posts ya analizada y agrupada."""
    from core.intelligence import IntelligenceEngine
    from core.orchestration.aggregation import build_clusters, cluster_to_dict

    motor = IntelligenceEngine(use_transformers_if_available=False)
    senales = [motor.analyze_signal(item_id=pid, title=titulo, body="", author="u",
                                    subreddit="SaaS", created_utc=1758000000.0)
               for pid, titulo in posts]
    return {
        "subreddit": "SaaS",
        "all_items": [{"id": pid, "title": t, "selftext": "", "author": "u",
                       "subreddit": "SaaS", "created_utc": 1758000000.0} for pid, t in posts],
        "all_signals": senales,
        "clusters": [cluster_to_dict(c) for c in build_clusters(senales)],
        "stats": {},
    }


@unittest.skipUnless(_postgres_available(), "PostgreSQL no disponible")
class TestPostgres(unittest.TestCase):

    def setUp(self):
        import psycopg

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        self.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")
        self.tmp = Path(tempfile.mkdtemp(prefix="rir_identidad_"))

    def tearDown(self):
        import psycopg

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        shutil.rmtree(self.tmp, ignore_errors=True)

    def filas(self, sql, params=()):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            conn.execute("SET search_path = radar, public")
            return conn.execute(sql, params).fetchall()

    def persistir(self, est):
        from core.storage.postgres_store import PostgresStore, run_async

        async def escribir():
            async with PostgresStore(dsn=self.dsn) as pg:
                return await pg.persist_state(est, data_source="demo")

        return run_async(escribir())

    def test_un_problema_que_gana_palabras_conserva_uuid_historial_y_validacion(self):
        from scripts.migrate import migrate

        migrate(self.dsn, RAIZ / "sql" / "migrations")
        base = [("p1", "The invoice export is broken again, all manual"),
                ("p2", "Invoice sync broken, manual work every week"),
                ("p3", "invoice totals broken, manual fixes all the time")]
        self.persistir(estado(base))
        (clave1, uuid1), = self.filas(
            "SELECT cluster_key, opportunity_id::text FROM opportunity_clusters")
        self.filas("INSERT INTO cluster_validations (tenant_id, opportunity_id, cluster_key, status) "
                   "SELECT tenant_id, opportunity_id, cluster_key, 'triaged' "
                   "FROM opportunity_clusters RETURNING 1")

        # Segundo escaneo: las mismas quejas y una más que añade palabras.
        self.persistir(estado([*base, ("p4", "invoice upload broken, manual and it takes hours")]))
        lecturas = self.filas("SELECT cluster_key, opportunity_id::text FROM opportunity_clusters "
                              "ORDER BY created_at")
        self.assertEqual(len(lecturas), 2)
        clave2, uuid2 = lecturas[1]
        self.assertNotEqual(clave2, clave1, "el test necesita que la clave cambie")
        self.assertEqual(uuid2, uuid1)
        (estado_tablero,), = self.filas(
            "SELECT DISTINCT validation_status::text FROM v_opportunity_board")
        self.assertEqual(estado_tablero, "triaged")

    def test_dos_problemas_distintos_tienen_uuid_distinto(self):
        from scripts.migrate import migrate

        migrate(self.dsn, RAIZ / "sql" / "migrations")
        self.persistir(estado([("p1", "The invoice export is broken again, all manual"),
                               ("p2", "Invoice sync broken, manual work every week")]))
        self.persistir(estado([("q1", "Onboarding is broken, I am drowning in tickets"),
                               ("q2", "our onboarding is broken and I am drowning in tickets")]))
        uuids = {u for (u,) in self.filas(
            "SELECT DISTINCT opportunity_id::text FROM opportunity_clusters")}
        self.assertEqual(len(uuids), 2)

    def test_la_migracion_conserva_el_historial_y_la_validacion_existentes(self):
        from scripts.migrate import migrate

        anteriores = self.tmp / "hasta_007"
        anteriores.mkdir()
        for sql in sorted((RAIZ / "sql" / "migrations").glob("00[1-7]_*.sql")):
            shutil.copy(sql, anteriores / sql.name)
        migrate(self.dsn, anteriores)
        self.filas(
            "WITH r AS (INSERT INTO pipeline_runs (tenant_id, subreddit_name, status) "
            "SELECT id, 'SaaS', 'completed' FROM tenants WHERE slug = 'local' RETURNING id, tenant_id) "
            "INSERT INTO opportunity_clusters (tenant_id, run_id, cluster_key, label, intent_type, "
            "mention_count, community_count, created_at) "
            "SELECT tenant_id, id, 'complaint:invoice', 'x', 'complaint', 1, 1, now() - interval '1 day' "
            "FROM r RETURNING 1")
        self.filas(
            "WITH r AS (INSERT INTO pipeline_runs (tenant_id, subreddit_name, status) "
            "SELECT id, 'SaaS', 'completed' FROM tenants WHERE slug = 'local' RETURNING id, tenant_id) "
            "INSERT INTO opportunity_clusters (tenant_id, run_id, cluster_key, label, intent_type, "
            "mention_count, community_count) "
            "SELECT tenant_id, id, 'complaint:invoice', 'x', 'complaint', 2, 1 FROM r RETURNING 1")
        self.filas("INSERT INTO cluster_validations (tenant_id, cluster_key, status, validated_at) "
                   "SELECT id, 'complaint:invoice', 'validated', now() FROM tenants "
                   "WHERE slug = 'local' RETURNING 1")

        migrate(self.dsn, RAIZ / "sql" / "migrations")
        uuids = {u for (u,) in self.filas(
            "SELECT DISTINCT opportunity_id::text FROM opportunity_clusters")}
        self.assertEqual(len(uuids), 1)
        (validacion,), = self.filas("SELECT opportunity_id::text FROM cluster_validations")
        self.assertEqual({validacion}, uuids)
        estados = {e for (e,) in self.filas(
            "SELECT validation_status::text FROM v_opportunity_board")}
        self.assertEqual(estados, {"validated"})


if __name__ == "__main__":
    unittest.main()
