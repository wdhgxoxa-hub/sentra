#!/usr/bin/env python
"""
Gestor de Migraciones (resolución de la deuda D9)
=================================================

Aplica migraciones SQL versionadas de forma determinista y transaccional,
llevando el control en una tabla `schema_migrations`.

Por qué no Alembic
------------------
Alembic vive sobre SQLAlchemy, y este proyecto no usa ORM: el esquema se
escribe en SQL a mano porque usa tipos y construcciones (ENUM, columnas
`tsvector` generadas, índices parciales, políticas RLS) que un ORM
expresaría peor. Traer SQLAlchemy entero para ordenar archivos `.sql` sería
pagar una dependencia grande por un problema pequeño.

Garantías
---------
- **Orden numérico**, no alfabético: 010 va después de 002.
- **Una transacción por migración**: o entra entera o no entra. Una
  migración rota no deja la base a medio migrar ni se registra como
  aplicada.
- **Huella de contenido**: si alguien edita una migración ya aplicada, el
  gestor se niega a seguir. La base no contendría lo que el archivo dice.

Uso
---
    python scripts/migrate.py status
    python scripts/migrate.py up
    python scripts/migrate.py up --dry-run
    python scripts/migrate.py up --dsn "host=... dbname=..."
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MIGRATIONS_DIR = PROJECT_ROOT / "sql" / "migrations"

# La tabla de control vive en `public`, no en `radar`: el propio esquema
# `radar` lo crea la primera migración, así que no puede alojar su control.
MIGRATIONS_TABLE = "public.schema_migrations"

MIGRATION_FILENAME = re.compile(r"^(\d{3,})_([a-z0-9_]+)\.sql$")



class MigrationError(RuntimeError):
    """Fallo al descubrir, planificar o aplicar una migración."""


class ChecksumMismatch(MigrationError):
    """Una migración ya aplicada ha cambiado de contenido."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path

    @property
    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")

    @property
    def checksum(self) -> str:
        return compute_checksum(self.sql)

    def __str__(self) -> str:
        return f"{self.version:03d}_{self.name}"


def compute_checksum(sql: str) -> str:
    """
    Huella del contenido de una migración.

    Se calcula sobre el texto con finales de línea LF (R-A). Git entrega el
    archivo con CRLF o LF según la configuración de cada clon; si eso
    cambiara la huella, una migración ya aplicada parecería editada en otro
    equipo. No se confía en que quien lee el archivo lo normalice: se hace
    aquí, que es donde importa.
    """
    normalizado = sql.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()


def discover_migrations(
    directory: str | Path | None = None,
) -> list[Migration]:
    """
    Lee el directorio de migraciones y las devuelve ordenadas por versión.

    Los archivos que no siguen el patrón `NNN_nombre.sql` se ignoran en
    silencio: así caben READMEs o borradores sin romper nada.
    """
    directory = Path(directory or DEFAULT_MIGRATIONS_DIR)
    if not directory.is_dir():
        raise MigrationError(f"No existe el directorio de migraciones: {directory}")

    migrations: list[Migration] = []
    seen: dict[int, str] = {}

    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        match = MIGRATION_FILENAME.match(path.name)
        if not match:
            continue

        version = int(match.group(1))
        name = match.group(2)

        if version in seen:
            raise MigrationError(
                f"Version {version} duplicada: '{seen[version]}' y '{path.name}'. "
                "Cada migracion debe tener un numero unico."
            )
        seen[version] = path.name
        migrations.append(Migration(version=version, name=name, path=path))

    migrations.sort(key=lambda m: m.version)
    return migrations


def pending_migrations(
    migrations: Sequence[Migration],
    applied: dict[int, str],
) -> list[Migration]:
    """
    Calcula qué queda por aplicar.

    Raises:
        ChecksumMismatch: si una migración ya aplicada cambió de contenido.
    """
    pending: list[Migration] = []

    for migration in migrations:
        if migration.version not in applied:
            pending.append(migration)
            continue

        if applied[migration.version] != migration.checksum:
            raise ChecksumMismatch(
                f"La migracion {migration} ya esta aplicada pero su contenido "
                "ha cambiado. La base de datos no contiene lo que el archivo "
                "dice contener. Crea una migracion nueva en lugar de editar "
                "una aplicada."
            )

    return pending


def ensure_migrations_table(conn) -> None:
    """Crea la tabla de control si aún no existe."""
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} (
            version     integer PRIMARY KEY,
            name        text NOT NULL,
            checksum    text NOT NULL,
            applied_at  timestamptz NOT NULL DEFAULT now(),
            duration_ms integer NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()


def applied_migrations(conn) -> dict[int, str]:
    """Devuelve `{version: checksum}` de lo ya aplicado."""
    rows = conn.execute(
        f"SELECT version, checksum FROM {MIGRATIONS_TABLE} ORDER BY version"
    ).fetchall()
    return {int(row[0]): str(row[1]) for row in rows}


def apply_migration(conn, migration: Migration) -> int:
    """
    Aplica una migración y la registra, todo dentro de una transacción.

    Returns:
        Milisegundos que tardó.

    Raises:
        MigrationError: si el SQL falla. La transacción se revierte, de modo
            que ni los cambios ni el registro llegan a existir.
    """
    started = time.monotonic()
    try:
        conn.execute(migration.sql)
        duration_ms = int((time.monotonic() - started) * 1000)
        conn.execute(
            f"""
            INSERT INTO {MIGRATIONS_TABLE} (version, name, checksum, duration_ms)
            VALUES (%s, %s, %s, %s)
            """,
            (migration.version, migration.name, migration.checksum, duration_ms),
        )
        conn.commit()
        return duration_ms
    except Exception as exc:
        conn.rollback()
        raise MigrationError(f"Fallo aplicando {migration}: {exc}") from exc


class AppliedMigration(TypedDict):
    migration: str
    ms: int


class MigrationReport(TypedDict):
    """Lo que devuelven `migrate` y `status`."""

    dsn: str
    total: int
    already_applied: list[int]
    pending: list[str]
    applied: list[AppliedMigration]


#: Parámetro de sesión con la sal de autores (R9). Lo lee la migración 009
#: para hashear los autores antiguos igual que core.evidence.author.
AUTHOR_SALT_SETTING = "rir.author_salt"


def migrate(
    dsn: str | None = None,
    directory: str | Path | None = None,
    dry_run: bool = False,
    author_salt: str | None = None,
) -> MigrationReport:
    """
    Aplica todas las migraciones pendientes.

    `author_salt` solo hace falta si hay autores antiguos que hashear: una
    base nueva migra sin ella. No se imprime ni se guarda en la base; vive
    en la sesión mientras dura la migración.

    Returns:
        Un informe con lo aplicado, lo pendiente y lo que ya estaba.
    """
    import psycopg

    dsn = dsn or _default_dsn()
    migrations = discover_migrations(directory)

    with psycopg.connect(dsn) as conn:
        if author_salt:
            conn.execute("SELECT set_config(%s, %s, false)", (AUTHOR_SALT_SETTING, author_salt))
        ensure_migrations_table(conn)
        already = applied_migrations(conn)
        pending = pending_migrations(migrations, already)

        report: MigrationReport = {
            "dsn": _redact(dsn),
            "total": len(migrations),
            "already_applied": sorted(already),
            "pending": [str(m) for m in pending],
            "applied": [],
        }

        if dry_run:
            return report

        for migration in pending:
            duration = apply_migration(conn, migration)
            logger.info("Aplicada %s (%d ms)", migration, duration)
            report["applied"].append({"migration": str(migration), "ms": duration})

        # El informe describe el estado RESULTANTE, no el de partida: decir
        # "pendientes: 001" justo después de haber aplicado 001 confunde.
        already = applied_migrations(conn)
        report["already_applied"] = sorted(already)
        report["pending"] = [str(m) for m in pending_migrations(migrations, already)]

        return report


def status(
    dsn: str | None = None,
    directory: str | Path | None = None,
) -> MigrationReport:
    """Informe de situación, sin aplicar nada."""
    return migrate(dsn=dsn, directory=directory, dry_run=True)


def _raiz_en_la_ruta() -> None:
    """Ejecutado como `python scripts/migrate.py`, la raíz no está en la ruta:
    se pone antes de importar nada de `core`."""
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))


def _default_dsn() -> str:
    """La misma resolución que el resto de la aplicación (AUD2-011)."""
    _raiz_en_la_ruta()
    from core.storage.postgres_store import resolver_dsn

    return resolver_dsn()


def _author_salt() -> str:
    _raiz_en_la_ruta()
    from core.evidence.author import load_or_create_salt

    return load_or_create_salt()


def _redact(dsn: str) -> str:
    """Oculta la contraseña del DSN antes de imprimirlo: `password=` y la de
    una URL (`postgresql://usuario:clave@…`), la forma canónica (AUD2-011)."""
    sin_clave = re.sub(r"password=\S+", "password=***", dsn)
    return re.sub(r"(://[^:/@\s]+:)[^@\s]+@", r"\1***@", sin_clave)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gestor de migraciones de SENTRA"
    )
    parser.add_argument("command", choices=["up", "status"],
                        help="'up' aplica lo pendiente; 'status' solo informa")
    parser.add_argument("--dsn", default=None, help="cadena de conexion a PostgreSQL")
    parser.add_argument("--dir", default=None, dest="directory",
                        help="directorio de migraciones")
    parser.add_argument("--dry-run", action="store_true",
                        help="con 'up', muestra lo que haria sin tocar la base")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        solo_mirar = args.dry_run or args.command == "status"
        report = migrate(
            dsn=args.dsn,
            directory=args.directory,
            dry_run=solo_mirar,
            # La sal de esta instalación (se crea la primera vez); solo al aplicar.
            author_salt=None if solo_mirar else _author_salt(),
        )
    except MigrationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"base de datos    : {report['dsn']}")
    print(f"migraciones      : {report['total']}")
    print(f"ya aplicadas     : {report['already_applied'] or 'ninguna'}")
    print(f"pendientes       : {report['pending'] or 'ninguna'}")

    applied = report["applied"]
    if applied:
        print("\naplicadas ahora:")
        for item in applied:
            print(f"   {item['migration']}  ({item['ms']} ms)")
    elif args.command == "up" and not args.dry_run:
        print("\nla base ya estaba al dia.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
