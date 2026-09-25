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

Lo ejecuta Walter una vez, conectado como `postgres` (libpq lee el pgpass
compartido; este script nunca lo escribe). Las contraseñas se teclean aquí
(getpass) y no llegan en claro al servidor: se envía el verificador
SCRAM-SHA-256 calculado en local, así no quedan en el log de PostgreSQL. Se
escriben solo en `%LOCALAPPDATA%\\SENTRA\\pgpass.conf`, con permisos solo para
el usuario de Windows (icacls sin herencia).

La propiedad se traspasa con ALTER ... OWNER: no se toca ningún dato.

Uso
---
    python -m scripts.rol_sentra --en-seco     # enseña las sentencias, no cambia nada
    python -m scripts.rol_sentra               # crea los roles, traspasa y escribe el pgpass
    python -m scripts.rol_sentra --deshacer    # devuelve todo a postgres y borra los roles
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
from pathlib import Path
from typing import Any

from core.rutas import ruta_pgpass

BASE = "reddit_intelligence_radar"
OWNER = "sentra_owner"
PRUEBAS = "sentra_pruebas"
#: Bases desechables de los tests (tests/test_*.py las llaman rir_*_test).
PATRON_PRUEBAS = r"rir\_%\_test"
ADMIN_DSN = "host=localhost port=5432 user=postgres dbname=postgres"
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


def escribir_pgpass(lineas: Sequence[str], *, ruta: Path | None = None) -> Path:
    """Escribe el pgpass de SENTRA y le quita la herencia de permisos. Se niega
    a escribir en cualquier otro sitio (el compartido solo se lee)."""
    destino = ruta if ruta is not None else ruta_pgpass()
    if destino.resolve() != ruta_pgpass().resolve():
        raise ValueError(f"solo se escribe el pgpass de SENTRA ({ruta_pgpass()}), no {destino}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(".tmp")
    temporal.write_text("".join(f"{linea}\n" for linea in lineas), encoding="utf-8", newline="\n")
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


def sentencias_de_propiedad(admin_dsn: str) -> tuple[list[str], list[str]]:
    """(Dentro de la base de SENTRA, a nivel de servidor): todo con ALTER ... OWNER."""
    dentro = _consultar(_en_base(admin_dsn, BASE), _OBJETOS)
    bases = [f"ALTER DATABASE {BASE} OWNER TO {OWNER}"] + [
        f'ALTER DATABASE "{nombre}" OWNER TO {PRUEBAS}'
        for nombre in _consultar(admin_dsn, "SELECT datname FROM pg_database WHERE datname LIKE %s "
                                 "AND datdba = 'postgres'::regrole ORDER BY 1", (PATRON_PRUEBAS,))
    ]
    return dentro, bases


def _ejecutar(dsn: str, sentencias: Sequence[str]) -> None:
    """Todas en una transacción: o entran todas o ninguna."""
    import psycopg

    with psycopg.connect(dsn) as conn, conn.transaction():
        for sentencia in sentencias:
            conn.execute(sentencia.encode("utf-8"))


def _roles_existentes(admin_dsn: str) -> list[str]:
    return _consultar(admin_dsn, "SELECT rolname FROM pg_roles WHERE rolname IN (%s, %s) ORDER BY 1",
                      (OWNER, PRUEBAS))


# --- Órdenes ---------------------------------------------------------------


def en_seco(admin_dsn: str) -> int:
    existentes = _roles_existentes(admin_dsn)
    dentro, bases = sentencias_de_propiedad(admin_dsn)
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
    print(f"   y permisos: {' '.join(orden_icacls(ruta_pgpass(), '<tu usuario de Windows>'))}")
    print("\nEn seco: no se ha cambiado nada.")
    return 0


def crear(admin_dsn: str) -> int:
    existentes = _roles_existentes(admin_dsn)
    if existentes:
        print(f"Ya existen {existentes}: nada que crear (--deshacer para empezar de cero).", file=sys.stderr)
        return 1
    clave_owner = _pedir_clave(OWNER)
    clave_pruebas = _pedir_clave(PRUEBAS)
    _ejecutar(admin_dsn, sentencias_de_roles(verificador_scram(clave_owner), verificador_scram(clave_pruebas)))
    print("1) Roles creados.")
    dentro, bases = sentencias_de_propiedad(admin_dsn)
    _ejecutar(_en_base(admin_dsn, BASE), dentro)
    print(f"2) {len(dentro)} objetos de {BASE} traspasados a {OWNER}.")
    _ejecutar(admin_dsn, bases)
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


def deshacer(admin_dsn: str) -> int:
    """Devuelve a postgres todo lo de los roles de SENTRA y los borra."""
    existentes = _roles_existentes(admin_dsn)
    bases = [BASE, "postgres"] + _consultar(admin_dsn, "SELECT datname FROM pg_database WHERE datname LIKE %s",
                                            (PATRON_PRUEBAS,))
    for base in dict.fromkeys(bases):
        _ejecutar(_en_base(admin_dsn, base), [f"REASSIGN OWNED BY {r} TO postgres" for r in existentes]
                  + [f"DROP OWNED BY {r}" for r in existentes])
    _ejecutar(admin_dsn, [f"DROP ROLE {r}" for r in existentes])
    ruta_pgpass().unlink(missing_ok=True)
    print(f"Deshecho: roles {existentes or 'ninguno'} borrados y {ruta_pgpass()} retirado.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Roles propios de SENTRA en PostgreSQL")
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--en-seco", action="store_true", help="enseña las sentencias sin cambiar nada")
    modo.add_argument("--deshacer", action="store_true", help="devuelve todo a postgres y borra los roles")
    parser.add_argument("--admin-dsn", default=ADMIN_DSN, help="conexión de superusuario (libpq lee su pgpass)")
    args = parser.parse_args(argv)
    if args.en_seco:
        return en_seco(args.admin_dsn)
    if args.deshacer:
        return deshacer(args.admin_dsn)
    return crear(args.admin_dsn)


if __name__ == "__main__":
    sys.exit(main())
