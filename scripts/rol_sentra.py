#!/usr/bin/env python
"""
Roles propios de SENTRA en PostgreSQL
=====================================

El 2026-09-24 otro proyecto reescribió el pgpass.conf que comparten los
proyectos de esta máquina y SENTRA se quedó sin base a mitad de una
compuerta. Desde entonces SENTRA tiene sus roles y su propio pgpass:

- `sentra_owner`: dueño de la base `reddit_intelligence_radar`, del esquema
  `radar` y de sus objetos. Lo usan la app, las migraciones y el humo.
  Sin superusuario y sin crear bases.
- `sentra_pruebas`: solo CREATEDB, para las bases desechables de los tests.

Lo ejecuta Walter una vez, con su usuario, como administrador `postgres`:
- Windows (por defecto): por TCP con `--admin-dsn` (libpq lee el pgpass
  compartido; este script nunca lo escribe).
- Linux (`--admin-sudo`): `postgres` no tiene contraseña y solo entra por el
  socket (peer). Las sentencias de administrador van por
  `sudo -u postgres psql`, con el SQL por stdin; sudo pide tu contraseña la
  primera vez. El script NO se lanza entero con sudo: el pgpass es el de tu
  usuario.
 Las contraseñas se teclean aquí
(getpass) y no llegan en claro al servidor: se envía el verificador
SCRAM-SHA-256 calculado en local, así no quedan en el log de PostgreSQL. Se
escriben solo en el pgpass de SENTRA (`core.rutas.ruta_pgpass()`), con
permisos solo para tu usuario: en Windows con icacls sin herencia; en Linux
el archivo nace ya con chmod 600 (libpq ignora un pgpass que otros pueden leer).

La propiedad se traspasa con ALTER ... OWNER: no se toca ningún dato.

Uso
---
    python -m scripts.rol_sentra --en-seco     # enseña las sentencias, no cambia nada
    python -m scripts.rol_sentra               # crea los roles, traspasa y escribe el pgpass
    python -m scripts.rol_sentra --deshacer    # devuelve todo a postgres y borra los roles

En Linux, lo mismo con `--admin-sudo`:
    python -m scripts.rol_sentra --admin-sudo --en-seco
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import os
import re
import secrets
import stringprep
import subprocess
import sys
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from core.rutas import ruta_pgpass

BASE = "reddit_intelligence_radar"
OWNER = "sentra_owner"
PRUEBAS = "sentra_pruebas"
#: Bases desechables de los tests (tests/test_*.py las llaman rir_*_test).
PATRON_PRUEBAS = r"rir\_%\_test"
ADMIN_DSN = "host=localhost port=5432 user=postgres dbname=postgres"
#: Linux: postgres entra por el socket con peer. -X sin psqlrc, -At una fila
#: por línea sin adornos, ON_ERROR_STOP para no seguir tras un error.
ORDEN_SUDO = ("sudo", "-u", "postgres", "psql", "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1")
ITERACIONES = 4096

_ATRIBUTOS = "LOGIN NOSUPERUSER NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT"


# --- Contraseñas -----------------------------------------------------------


def _saslprep(clave: str) -> str:
    """SASLprep (RFC 4013) como pg_saslprep: si la clave tiene caracteres
    prohibidos, PostgreSQL usa los bytes tal cual, y aquí también."""
    mapeada = "".join(" " if stringprep.in_table_c12(c) else c
                      for c in clave if not stringprep.in_table_b1(c))
    normal = unicodedata.normalize("NFKC", mapeada)
    prohibidos = (stringprep.in_table_c12, stringprep.in_table_c21_c22, stringprep.in_table_c3,
                  stringprep.in_table_c4, stringprep.in_table_c5, stringprep.in_table_c6,
                  stringprep.in_table_c7, stringprep.in_table_c8, stringprep.in_table_c9,
                  stringprep.in_table_a1)
    if any(regla(c) for c in normal for regla in prohibidos):
        return clave
    return normal


def verificador_scram(clave: str, *, sal: bytes | None = None, iteraciones: int = ITERACIONES) -> str:
    """Lo que PostgreSQL guarda de una contraseña SCRAM-SHA-256 (RFC 5802/7677)."""
    sal = sal if sal is not None else secrets.token_bytes(16)
    salada = hashlib.pbkdf2_hmac("sha256", _saslprep(clave).encode("utf-8"), sal, iteraciones)
    clave_cliente = hmac.new(salada, b"Client Key", hashlib.sha256).digest()
    guardada = hashlib.sha256(clave_cliente).digest()
    servidor = hmac.new(salada, b"Server Key", hashlib.sha256).digest()

    def b64(datos: bytes) -> str:
        return base64.b64encode(datos).decode("ascii")

    return f"SCRAM-SHA-256${iteraciones}:{b64(sal)}${b64(guardada)}:{b64(servidor)}"


def _escapar(campo: str) -> str:
    return campo.replace("\\", "\\\\").replace(":", "\\:")


def linea_pgpass(base: str, usuario: str, clave: str, host: str = "localhost", puerto: int = 5432) -> str:
    return ":".join((host, str(puerto), _escapar(base), _escapar(usuario), _escapar(clave)))


def orden_icacls(ruta: Path, usuario: str) -> list[str]:
    """Sin herencia y con control total solo para `usuario`: nadie más la lee."""
    return ["icacls", str(ruta), "/inheritance:r", "/grant:r", f"{usuario}:(F)"]


def _abrir_privado(ruta: Path) -> Any:
    """Abre `ruta` para escribir. En POSIX nace con 0600 y, si ya existía,
    se deja en 0600 antes de escribir nada: la clave nunca queda legible.
    (sys.platform y no os.name: así mypy sabe que fchmod no corre en Windows.)"""
    if sys.platform == "win32":
        return ruta.open("w", encoding="utf-8", newline="\n")
    descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
    except BaseException:
        os.close(descriptor)
        raise
    return os.fdopen(descriptor, "w", encoding="utf-8", newline="\n")


def escribir_pgpass(lineas: Sequence[str], *, ruta: Path | None = None) -> Path:
    """Escribe el pgpass de SENTRA solo para tu usuario (Windows: icacls sin
    herencia; POSIX: 0600). Se niega a escribir en cualquier otro sitio (el
    compartido solo se lee)."""
    destino = ruta if ruta is not None else ruta_pgpass()
    if destino.resolve() != ruta_pgpass().resolve():
        raise ValueError(f"solo se escribe el pgpass de SENTRA ({ruta_pgpass()}), no {destino}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(".tmp")
    with _abrir_privado(temporal) as archivo:
        archivo.write("".join(f"{linea}\n" for linea in lineas))
    if os.name == "nt":
        usuario = subprocess.run(["whoami"], capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run(orden_icacls(temporal, usuario), check=True, capture_output=True, text=True)
    os.replace(temporal, destino)
    return destino


def _pedir_clave(rol: str) -> str:
    while True:
        clave = getpass.getpass(f"Contraseña nueva para {rol}: ")
        if not clave or "\n" in clave:
            print("  Vacía o con saltos de línea: otra vez.")
            continue
        if getpass.getpass(f"Repite la contraseña de {rol}: ") != clave:
            print("  No coinciden: otra vez.")
            continue
        return clave


# --- Sentencias -----------------------------------------------------------


def _literal(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def sentencias_de_roles(verificador_owner: str, verificador_pruebas: str) -> list[str]:
    return [
        f"CREATE ROLE {OWNER} {_ATRIBUTOS} NOCREATEDB PASSWORD {_literal(verificador_owner)}",
        f"CREATE ROLE {PRUEBAS} {_ATRIBUTOS} CREATEDB PASSWORD {_literal(verificador_pruebas)}",
    ]


def para_mostrar(sentencias: Sequence[str]) -> list[str]:
    """Las sentencias sin el verificador: en seco no se enseña nada secreto."""
    return [re.sub(r"PASSWORD '[^']*'", "PASSWORD '<verificador SCRAM, no se muestra>'", s)
            for s in sentencias]


#: Objetos de SENTRA que hoy son de postgres, sin los de las extensiones (esos
#: siguen con su extensión) ni las secuencias de columnas (siguen a su tabla).
_OBJETOS = """
WITH de_extension AS (SELECT objid FROM pg_depend WHERE deptype = 'e')
SELECT format('ALTER %s %I.%I OWNER TO {owner}',
              CASE c.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW'
                             WHEN 'S' THEN 'SEQUENCE' WHEN 'c' THEN 'TYPE' ELSE 'TABLE' END,
              n.nspname, c.relname)
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname IN ('radar', 'public') AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f', 'c')
   AND c.relowner = 'postgres'::regrole
   AND c.oid NOT IN (SELECT objid FROM de_extension)
   AND NOT (c.relkind = 'S' AND EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass
                                          AND d.objid = c.oid AND d.deptype IN ('a', 'i')))
UNION ALL
SELECT format('ALTER TYPE %I.%I OWNER TO {owner}', n.nspname, t.typname)
  FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
 WHERE n.nspname IN ('radar', 'public') AND t.typtype IN ('e', 'd', 'r', 'm')
   AND t.typowner = 'postgres'::regrole AND t.oid NOT IN (SELECT objid FROM de_extension)
UNION ALL
SELECT format('ALTER ROUTINE %s OWNER TO {owner}', p.oid::regprocedure)
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname IN ('radar', 'public') AND p.proowner = 'postgres'::regrole
   AND p.oid NOT IN (SELECT objid FROM de_extension)
UNION ALL
SELECT format('ALTER SCHEMA %I OWNER TO {owner}', n.nspname)
  FROM pg_namespace n WHERE n.nspname IN ('radar', 'public') AND n.nspowner = 'postgres'::regrole
""".replace("{owner}", OWNER)


def _consultar(dsn: str, sql: str, params: Sequence[Any] | None = None) -> list[str]:
    import psycopg

    with psycopg.connect(dsn) as conn:
        return [str(fila[0]) for fila in conn.execute(sql, params).fetchall()]


def _en_base(dsn: str, base: str) -> str:
    return re.sub(r"dbname=\S+", f"dbname={base}", dsn)


def _ejecutar(dsn: str, sentencias: Sequence[str]) -> None:
    """Todas en una transacción: o entran todas o ninguna."""
    import psycopg

    with psycopg.connect(dsn) as conn, conn.transaction():
        for sentencia in sentencias:
            conn.execute(sentencia.encode("utf-8"))


class Administrador(Protocol):
    """Cómo se habla con PostgreSQL como `postgres`. `base` None = la de
    administración (la del DSN, o `postgres`)."""

    def consultar(self, base: str | None, sql: str, params: Sequence[str] = ()) -> list[str]: ...

    def ejecutar(self, base: str | None, sentencias: Sequence[str]) -> None:
        """Todas en una transacción: o entran todas o ninguna."""
        ...


@dataclass(frozen=True)
class AdminPorDsn:
    """Por TCP con psycopg (Windows, y lo de siempre)."""

    dsn: str

    def _dsn(self, base: str | None) -> str:
        return self.dsn if base is None else _en_base(self.dsn, base)

    def consultar(self, base: str | None, sql: str, params: Sequence[str] = ()) -> list[str]:
        return _consultar(self._dsn(base), sql, params or None)

    def ejecutar(self, base: str | None, sentencias: Sequence[str]) -> None:
        _ejecutar(self._dsn(base), sentencias)


def _con_literales(sql: str, params: Sequence[str]) -> str:
    """Pone cada parámetro como literal SQL escapado (_literal) en su %s."""
    if not params:
        return sql
    trozos = sql.split("%s")
    if len(trozos) != len(params) + 1 or "%%" in sql:
        raise ValueError(f"{len(params)} parámetros para {len(trozos) - 1} %s: {sql!r}")
    return "".join(t + _literal(str(p)) for t, p in zip(trozos, params, strict=False)) + trozos[-1]


@dataclass(frozen=True)
class AdminPorSudo:
    """Linux: `sudo -u postgres psql` por el socket. El SQL va por stdin, nunca
    en argv; las claves ya llegan solo como verificador SCRAM."""

    def _psql(self, base: str | None, sql: str) -> str:
        orden = [*ORDEN_SUDO, "-d", base or "postgres"]
        # cwd="/": postgres no puede entrar en tu carpeta y psql avisaría.
        return subprocess.run(orden, input=sql, text=True, encoding="utf-8", stdout=subprocess.PIPE,
                              check=True, cwd="/").stdout

    def consultar(self, base: str | None, sql: str, params: Sequence[str] = ()) -> list[str]:
        salida = self._psql(base, _con_literales(sql, params).rstrip().rstrip(";") + ";\n")
        return salida.splitlines()

    def ejecutar(self, base: str | None, sentencias: Sequence[str]) -> None:
        # ON_ERROR_STOP corta antes del COMMIT: psql sale y la transacción se deshace.
        self._psql(base, "BEGIN;\n" + "".join(f"{s};\n" for s in sentencias) + "COMMIT;\n")


def sentencias_de_propiedad(admin: Administrador) -> tuple[list[str], list[str]]:
    """(Dentro de la base de SENTRA, a nivel de servidor): todo con ALTER ... OWNER."""
    dentro = admin.consultar(BASE, _OBJETOS)
    bases = [f"ALTER DATABASE {BASE} OWNER TO {OWNER}"] + [
        f'ALTER DATABASE "{nombre}" OWNER TO {PRUEBAS}'
        for nombre in admin.consultar(None, "SELECT datname FROM pg_database WHERE datname LIKE %s "
                                      "AND datdba = 'postgres'::regrole ORDER BY 1", (PATRON_PRUEBAS,))
    ]
    return dentro, bases


def _roles_existentes(admin: Administrador) -> list[str]:
    return admin.consultar(None, "SELECT rolname FROM pg_roles WHERE rolname IN (%s, %s) ORDER BY 1",
                           (OWNER, PRUEBAS))


# --- Órdenes ---------------------------------------------------------------


def en_seco(admin: Administrador) -> int:
    existentes = _roles_existentes(admin)
    dentro, bases = sentencias_de_propiedad(admin)
    print(f"Roles ya existentes: {existentes or 'ninguno'}")
    print("\n1) Roles (servidor, una transacción):")
    for s in para_mostrar(sentencias_de_roles("x", "x")):
        print(f"   {s};")
    print(f"\n2) Propiedad dentro de {BASE} (una transacción, {len(dentro)} sentencias):")
    for s in dentro:
        print(f"   {s};")
    print(f"\n3) Propiedad de las bases (una transacción, {len(bases)} sentencias):")
    for s in bases:
        print(f"   {s};")
    print(f"\n4) Se escribe {ruta_pgpass()} con 2 líneas:")
    print(f"   localhost:5432:{BASE}:{OWNER}:<contraseña>")
    print(f"   localhost:5432:*:{PRUEBAS}:<contraseña>")
    print(f"   y permisos: {' '.join(_orden_de_permisos())}")
    print("\nEn seco: no se ha cambiado nada.")
    return 0


def _orden_de_permisos() -> list[str]:
    """Cómo queda el pgpass solo para tu usuario, para enseñarlo en seco."""
    if os.name == "nt":
        return orden_icacls(ruta_pgpass(), "<tu usuario de Windows>")
    return ["chmod", "600", str(ruta_pgpass()), "(nace así, antes de escribir la contraseña)"]


def crear(admin: Administrador) -> int:
    existentes = _roles_existentes(admin)
    if existentes:
        print(f"Ya existen {existentes}: nada que crear (--deshacer para empezar de cero).", file=sys.stderr)
        return 1
    clave_owner = _pedir_clave(OWNER)
    clave_pruebas = _pedir_clave(PRUEBAS)
    admin.ejecutar(None, sentencias_de_roles(verificador_scram(clave_owner), verificador_scram(clave_pruebas)))
    print("1) Roles creados.")
    dentro, bases = sentencias_de_propiedad(admin)
    admin.ejecutar(BASE, dentro)
    print(f"2) {len(dentro)} objetos de {BASE} traspasados a {OWNER}.")
    admin.ejecutar(None, bases)
    print(f"3) {len(bases)} bases traspasadas.")
    ruta = escribir_pgpass([linea_pgpass(BASE, OWNER, clave_owner), linea_pgpass("*", PRUEBAS, clave_pruebas)])
    print(f"4) {ruta} escrito, solo para tu usuario.")
    for rol, base in ((OWNER, BASE), (PRUEBAS, "postgres")):
        _consultar(f"host=localhost port=5432 user={rol} dbname={base} passfile='{_escapar_valor(ruta)}'",
                   "SELECT current_user")
        print(f"   {rol} entra en {base} con el pgpass de SENTRA: OK")
    return 0


def _escapar_valor(ruta: Path) -> str:
    return str(ruta).replace("\\", "\\\\").replace("'", "\\'")


def deshacer(admin: Administrador) -> int:
    """Devuelve a postgres todo lo de los roles de SENTRA y los borra."""
    existentes = _roles_existentes(admin)
    bases = [BASE, "postgres"] + admin.consultar(None, "SELECT datname FROM pg_database WHERE datname LIKE %s",
                                                 (PATRON_PRUEBAS,))
    for base in dict.fromkeys(bases):
        admin.ejecutar(base, [f"REASSIGN OWNED BY {r} TO postgres" for r in existentes]
                       + [f"DROP OWNED BY {r}" for r in existentes])
    admin.ejecutar(None, [f"DROP ROLE {r}" for r in existentes])
    ruta_pgpass().unlink(missing_ok=True)
    print(f"Deshecho: roles {existentes or 'ninguno'} borrados y {ruta_pgpass()} retirado.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Roles propios de SENTRA en PostgreSQL")
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--en-seco", action="store_true", help="enseña las sentencias sin cambiar nada")
    modo.add_argument("--deshacer", action="store_true", help="devuelve todo a postgres y borra los roles")
    acceso = parser.add_mutually_exclusive_group()
    acceso.add_argument("--admin-dsn", default=ADMIN_DSN, help="conexión de superusuario (libpq lee su pgpass)")
    acceso.add_argument("--admin-sudo", action="store_true",
                        help="Linux: las sentencias de administrador van por sudo -u postgres psql (socket, peer)")
    args = parser.parse_args(argv)
    if args.admin_sudo and sys.platform == "win32":
        parser.error("--admin-sudo es para Linux; en Windows usa --admin-dsn")
    admin: Administrador = AdminPorSudo() if args.admin_sudo else AdminPorDsn(args.admin_dsn)
    if args.en_seco:
        return en_seco(admin)
    if args.deshacer:
        return deshacer(admin)
    return crear(admin)


if __name__ == "__main__":
    sys.exit(main())
