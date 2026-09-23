"""
Registro y estado verificado de las fuentes (F2.4, F2.8)
=======================================================

Mismo principio que AUD-004: una fuente solo está «verificada» tras una
respuesta real de su API, con la hora de ese acceso. Si no está conectada,
no es origen de nada; el modo comercial excluye las que no permiten uso
comercial y lo dice.
"""

import os
import unittest
from datetime import UTC, datetime

from core.sources.base import CostModel, CredentialField, ProbeResult, SourceAdapter
from core.sources.registry import (
    InMemorySourcesState,
    active_sources,
    source_status,
)


class Publica(SourceAdapter):
    id = "publica"
    display_name = "Pública"
    terms_url = "https://example.com/t"
    commercial_use_allowed = True
    requires_credentials = False
    cost_model = CostModel(unit="request")

    async def probe(self):  # pragma: no cover - no se llama aquí
        raise NotImplementedError

    def search(self, query):  # pragma: no cover
        raise NotImplementedError


class ConClave(Publica):
    id = "conclave"
    display_name = "Con clave"
    requires_credentials = True
    credential_fields = (
        CredentialField(name="token", env_var="RIR_CONCLAVE_TOKEN"),
        CredentialField(name="extra", env_var="RIR_CONCLAVE_EXTRA", required=False),
    )


class SoloPersonal(Publica):
    id = "personal"
    display_name = "Solo personal"
    commercial_use_allowed = False


FUENTES = (Publica, ConClave, SoloPersonal)
HORA = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def ok():
    return ProbeResult(ok=True, detail="respuesta real", checked_at=HORA)


class TestEstado(unittest.TestCase):
    def setUp(self):
        self.guardado = InMemorySourcesState()

    def estado(self, fuente, env=None, comercial=False):
        return source_status(fuente, env or {}, self.guardado.get(fuente.id), comercial)

    def test_una_publica_sin_uso_real_esta_configurada_sin_verificar(self):
        self.assertEqual(self.estado(Publica).status, "configurada_sin_verificar")

    def test_sin_credenciales_obligatorias_no_esta_configurada(self):
        self.assertEqual(self.estado(ConClave).status, "no_configurada")
        # La opcional no hace falta.
        con = self.estado(ConClave, {"RIR_CONCLAVE_TOKEN": "x"})
        self.assertEqual(con.status, "configurada_sin_verificar")

    def test_solo_una_respuesta_real_la_verifica(self):
        self.guardado.record_probe("publica", ok())
        estado = self.estado(Publica)
        self.assertEqual((estado.status, estado.last_verified_at), ("verificada", HORA))

    def test_un_fallo_real_deja_error_con_codigo(self):
        self.guardado.record_probe("publica", ProbeResult(
            ok=False, code="source_auth_failed", detail="HTTP 401", checked_at=HORA))
        estado = self.estado(Publica)
        self.assertEqual((estado.status, estado.error_code), ("error", "source_auth_failed"))

    def test_deshabilitada_por_el_usuario_manda_sobre_todo(self):
        self.guardado.record_probe("publica", ok())
        self.guardado.set_disabled("publica", True)
        self.assertEqual(self.estado(Publica).status, "deshabilitada_por_usuario")

    def test_el_estado_dice_que_credenciales_tiene_sin_devolverlas(self):
        estado = self.estado(ConClave, {"RIR_CONCLAVE_TOKEN": "secreto-123"})
        campos = {c.name: c.configured for c in estado.credential_fields}
        self.assertEqual(campos, {"token": True, "extra": False})
        self.assertNotIn("secreto-123", estado.model_dump_json())

    def test_el_estado_lleva_el_coste_para_la_tarjeta(self):
        class DeCuota(Publica):
            id = "cuota"
            cost_model = CostModel(unit="quota_unit", per_request=100,
                                   note="10.000 unidades al día")

        estado = self.estado(DeCuota)
        self.assertEqual((estado.cost_unit, estado.cost_note),
                         ("quota_unit", "10.000 unidades al día"))


class TestActivas(unittest.TestCase):
    def test_solo_las_conectadas_y_habilitadas(self):
        guardado = InMemorySourcesState()
        guardado.set_disabled("personal", True)
        activas = active_sources(FUENTES, {}, guardado, commercial_mode=False)
        self.assertEqual([f.id for f in activas], ["publica"])

    def test_el_modo_comercial_excluye_las_de_uso_personal_y_lo_dice(self):
        guardado = InMemorySourcesState()
        activas = active_sources(FUENTES, {}, guardado, commercial_mode=True)
        self.assertEqual([f.id for f in activas], ["publica"])
        estado = source_status(SoloPersonal, {}, None, commercial_mode=True)
        self.assertTrue(estado.excluded_by_commercial_mode)
        self.assertFalse(source_status(SoloPersonal, {}, None, False).excluded_by_commercial_mode)


ADMIN_DSN = os.environ.get(
    "RIR_PG_ADMIN_DSN", "host=localhost port=5432 user=postgres dbname=postgres"
)
TEST_DB = "rir_sources_state_test"


def _postgres_available() -> bool:
    try:
        import psycopg
    except ImportError:
        return False
    try:
        with psycopg.connect(ADMIN_DSN, connect_timeout=3):
            return True
    except psycopg.Error:
        return False


@unittest.skipUnless(_postgres_available(), "PostgreSQL no disponible")
class TestEnPostgres(unittest.TestCase):
    """El repositorio de PostgreSQL cumple el mismo contrato que el de memoria."""

    @classmethod
    def setUpClass(cls):
        from pathlib import Path

        import psycopg

        from scripts.migrate import migrate

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        cls.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")
        migrate(cls.dsn, Path(__file__).resolve().parents[1] / "sql" / "migrations")

    @classmethod
    def tearDownClass(cls):
        import psycopg

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')

    def test_ida_y_vuelta(self):
        from core.sources.registry import PostgresSourcesState

        repo = PostgresSourcesState(self.dsn)
        repo.record_probe("hackernews", ok())
        repo.record_probe("github", ProbeResult(ok=False, code="source_auth_failed",
                                                detail="HTTP 401", checked_at=HORA))
        repo.set_disabled("github", True)
        repo.set_disabled("github", False)
        otra = PostgresSourcesState(self.dsn)
        hn = otra.get("hackernews")
        self.assertEqual((hn.status, hn.last_verified_at), ("verificada", HORA))
        gh = otra.get("github")
        self.assertEqual((gh.status, gh.error_code, gh.disabled), ("error", "source_auth_failed", False))
        self.assertIsNone(otra.get("mastodon"))


if __name__ == "__main__":
    unittest.main()
