"""
Suite de pruebas del gestor de migraciones (deuda D9)
=====================================================

Dos bloques, como en el adaptador:

1. Descubrimiento y planificación (siempre): orden, validación de nombres,
   huellas de contenido y cálculo de pendientes. Sin base de datos.
2. Aplicación real (se omite sin PostgreSQL): aplica sobre una base
   desechable y comprueba idempotencia, transaccionalidad y detección de
   migraciones alteradas después de aplicadas.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.migrate import (
    MIGRATIONS_TABLE,
    ChecksumMismatch,
    MigrationError,
    applied_migrations,
    compute_checksum,
    discover_migrations,
    ensure_migrations_table,
    migrate,
    pending_migrations,
)

ADMIN_DSN = os.environ.get(
    "RIR_PG_ADMIN_DSN", "host=localhost port=5432 user=postgres dbname=postgres"
)
TEST_DB = "rir_migrations_test"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_MIGRATIONS = PROJECT_ROOT / "sql" / "migrations"


def _postgres_available():
    try:
        import psycopg

        with psycopg.connect(ADMIN_DSN, connect_timeout=3):
            return True
    except Exception:
        return False


POSTGRES_AVAILABLE = _postgres_available()


class MigrationDirTestCase(unittest.TestCase):
    """Base que construye directorios de migraciones sintéticos."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="rir_mig_"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def write(self, filename, sql="SELECT 1;"):
        path = self.tmpdir / filename
        path.write_text(sql, encoding="utf-8")
        return path


class TestDiscovery(MigrationDirTestCase):

    def test_finds_migrations_in_a_directory(self):
        self.write("001_initial.sql")
        self.write("002_add_column.sql")
        self.assertEqual(len(discover_migrations(self.tmpdir)), 2)

    def test_orders_numerically_not_alphabetically(self):
        """010 va después de 002, aunque como texto sea al revés."""
        self.write("001_a.sql")
        self.write("002_b.sql")
        self.write("010_c.sql")
        versions = [m.version for m in discover_migrations(self.tmpdir)]
        self.assertEqual(versions, [1, 2, 10])

    def test_parses_version_and_name(self):
        self.write("007_add_indexes.sql")
        migration = discover_migrations(self.tmpdir)[0]
        self.assertEqual(migration.version, 7)
        self.assertEqual(migration.name, "add_indexes")

    def test_ignores_files_that_are_not_migrations(self):
        self.write("001_initial.sql")
        self.write("README.md", "# notas")
        self.write("borrador.sql")
        self.assertEqual(len(discover_migrations(self.tmpdir)), 1)

    def test_duplicate_version_is_rejected(self):
        self.write("001_uno.sql")
        self.write("001_otro.sql")
        with self.assertRaises(MigrationError):
            discover_migrations(self.tmpdir)

    def test_missing_directory_is_an_error(self):
        with self.assertRaises(MigrationError):
            discover_migrations(self.tmpdir / "no_existe")

    def test_empty_directory_yields_nothing(self):
        self.assertEqual(discover_migrations(self.tmpdir), [])

    def test_real_migrations_directory_has_the_initial_schema(self):
        migrations = discover_migrations(REAL_MIGRATIONS)
        self.assertGreaterEqual(len(migrations), 1)
        self.assertEqual(migrations[0].version, 1)
        self.assertEqual(migrations[0].name, "initial_schema")

    def test_real_migrations_have_contiguous_versions(self):
        """Un hueco en la numeracion suele ser una migracion perdida."""
        versions = [m.version for m in discover_migrations(REAL_MIGRATIONS)]
        self.assertEqual(versions, list(range(1, len(versions) + 1)))


class TestChecksum(MigrationDirTestCase):

    def test_checksum_is_deterministic(self):
        self.assertEqual(compute_checksum("SELECT 1;"), compute_checksum("SELECT 1;"))

    def test_checksum_changes_with_content(self):
        self.assertNotEqual(compute_checksum("SELECT 1;"), compute_checksum("SELECT 2;"))

    def test_migration_exposes_its_checksum(self):
        path = self.write("001_x.sql", "SELECT 42;")
        migration = discover_migrations(self.tmpdir)[0]
        self.assertEqual(migration.checksum, compute_checksum("SELECT 42;"))


class TestPending(MigrationDirTestCase):

    def setUp(self):
        super().setUp()
        self.write("001_a.sql", "SELECT 1;")
        self.write("002_b.sql", "SELECT 2;")
        self.migrations = discover_migrations(self.tmpdir)

    def test_nothing_applied_means_everything_pending(self):
        self.assertEqual(len(pending_migrations(self.migrations, {})), 2)

    def test_applied_migrations_are_skipped(self):
        applied = {1: self.migrations[0].checksum}
        pending = pending_migrations(self.migrations, applied)
        self.assertEqual([m.version for m in pending], [2])

    def test_all_applied_means_nothing_pending(self):
        applied = {m.version: m.checksum for m in self.migrations}
        self.assertEqual(pending_migrations(self.migrations, applied), [])

    def test_altered_applied_migration_is_rejected(self):
        """
        Editar una migración ya aplicada rompe la reproducibilidad: la base
        de datos no contiene lo que el archivo dice que contiene.
        """
        applied = {1: "huella_que_no_corresponde"}
        with self.assertRaises(ChecksumMismatch):
            pending_migrations(self.migrations, applied)


@unittest.skipUnless(POSTGRES_AVAILABLE, "PostgreSQL no disponible")
class TestApplyingMigrations(unittest.TestCase):
    """Aplicación real contra una base desechable."""

    def setUp(self):
        import psycopg

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        self.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")

    def tearDown(self):
        import psycopg

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')

    def _query(self, sql, params=()):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            return conn.execute(sql, params).fetchall()

    def test_applies_every_pending_migration(self):
        """Se compara con las migraciones que hay, no con un numero fijo:
        el test debe seguir siendo valido cuando se anada la 003."""
        total = len(discover_migrations(REAL_MIGRATIONS))
        report = migrate(self.dsn, REAL_MIGRATIONS)
        self.assertEqual(len(report["applied"]), total)

        # Se comprueba que estan las tablas del dominio, no cuantas hay:
        # un conteo fijo se rompe con cada migracion nueva.
        tables = {
            r[0] for r in self._query(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'radar' AND table_type = 'BASE TABLE'"
            )
        }
        self.assertTrue(
            {"tenants", "subreddits", "pipeline_runs", "raw_posts",
             "raw_comments", "analyzed_signals", "jtbd_opportunities"} <= tables
        )

    def test_creates_the_control_table(self):
        migrate(self.dsn, REAL_MIGRATIONS)
        rows = self._query(
            f"SELECT version, name, checksum FROM {MIGRATIONS_TABLE} ORDER BY version"
        )
        self.assertEqual(rows[0][0], 1)
        self.assertEqual(rows[0][1], "initial_schema")
        self.assertTrue(rows[0][2])

    def test_records_how_long_each_migration_took(self):
        migrate(self.dsn, REAL_MIGRATIONS)
        rows = self._query(f"SELECT duration_ms FROM {MIGRATIONS_TABLE}")
        self.assertGreaterEqual(rows[0][0], 0)

    def test_running_twice_applies_nothing_new(self):
        total = len(discover_migrations(REAL_MIGRATIONS))
        migrate(self.dsn, REAL_MIGRATIONS)
        second = migrate(self.dsn, REAL_MIGRATIONS)
        self.assertEqual(second["applied"], [])
        self.assertEqual(len(second["already_applied"]), total)
        self.assertEqual(second["pending"], [])

    def test_dry_run_changes_nothing(self):
        total = len(discover_migrations(REAL_MIGRATIONS))
        report = migrate(self.dsn, REAL_MIGRATIONS, dry_run=True)
        self.assertEqual(len(report["pending"]), total)
        tables = self._query(
            "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'radar'"
        )
        self.assertEqual(tables[0][0], 0, "dry-run no debe crear nada")

    def test_a_failing_migration_leaves_no_trace(self):
        """Cada migración va en su transacción: o entra entera o no entra."""
        tmpdir = Path(tempfile.mkdtemp(prefix="rir_bad_"))
        try:
            (tmpdir / "001_ok.sql").write_text(
                "CREATE TABLE buena (id int);", encoding="utf-8"
            )
            (tmpdir / "002_rota.sql").write_text(
                "CREATE TABLE mala (id int); ESTO NO ES SQL;", encoding="utf-8"
            )
            with self.assertRaises(MigrationError):
                migrate(self.dsn, tmpdir)

            applied = self._query(f"SELECT version FROM {MIGRATIONS_TABLE}")
            self.assertEqual([r[0] for r in applied], [1],
                             "la primera entra, la rota no")
            existe = self._query(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'mala'"
            )
            self.assertEqual(existe[0][0], 0, "la tabla de la migracion rota no existe")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_altering_an_applied_migration_is_detected(self):
        tmpdir = Path(tempfile.mkdtemp(prefix="rir_alt_"))
        try:
            path = tmpdir / "001_algo.sql"
            path.write_text("CREATE TABLE algo (id int);", encoding="utf-8")
            migrate(self.dsn, tmpdir)

            path.write_text("CREATE TABLE algo (id bigint);", encoding="utf-8")
            with self.assertRaises(ChecksumMismatch):
                migrate(self.dsn, tmpdir)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_applied_migrations_reads_back_what_was_written(self):
        import psycopg

        migrate(self.dsn, REAL_MIGRATIONS)
        with psycopg.connect(self.dsn) as conn:
            ensure_migrations_table(conn)
            applied = applied_migrations(conn)
        self.assertIn(1, applied)

    def test_the_schema_is_usable_after_migrating(self):
        """Prueba de humo: el tenant por defecto existe y se puede consultar."""
        migrate(self.dsn, REAL_MIGRATIONS)
        rows = self._query("SELECT slug FROM radar.tenants")
        self.assertIn("local", [r[0] for r in rows])

    def test_the_cluster_tables_exist_after_migrating(self):
        migrate(self.dsn, REAL_MIGRATIONS)
        rows = self._query(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'radar' AND table_name LIKE 'opportunity_cluster%%'"
        )
        names = {r[0] for r in rows}
        self.assertEqual(
            names, {"opportunity_clusters", "opportunity_cluster_signals"}
        )


if __name__ == "__main__":
    unittest.main()
