"""
Lo que el servidor MCP lee y escribe (core/mcp/servidor.py)
==========================================================

Sin el motor: lee la base y la carpeta de dossiers, así que funciona con
SENTRA cerrada, y nunca llama a Gemini ni a las fuentes. Reutiliza las mismas
lecturas que la interfaz (el Radar con su filtro de privacidad R9, el resumen
de cada escaneo) para que Claude vea lo mismo que Walter.

Lo único que escribe es una propuesta de escaneo (`scan_requests`, migración
021): no gasta nada. El escaneo solo arranca si Walter pulsa «Lanzar» en la
ventana de SENTRA (decisión del 2026-10-09; el motor sigue sin aceptar a
ningún otro proceso, D-B).
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import psycopg
from pydantic import ValidationError

from core.documents.almacen import AlmacenDeDocumentos
from core.rutas import ruta_documentos
from core.sources.profile import ScanProfile, idioma_de
from core.storage.postgres_store import (
    DEFAULT_TENANT_ID,
    PostgresStore,
    resolver_dsn,
    run_async,
)

_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
#: Cuántos escaneos devuelve `escaneos` como mucho.
ESCANEOS_MAX = 50
MOTIVO_MAX = 500


class DatoInvalido(ValueError):
    """Lo que pidió Claude no vale (un id mal formado, un perfil incompleto...)."""


class DatosSentra:
    def __init__(self, dsn: str | None = None, documentos: Path | None = None,
                 tenant_id: str = DEFAULT_TENANT_ID) -> None:
        self._dsn = resolver_dsn(dsn)
        self._almacen = AlmacenDeDocumentos(documentos or ruta_documentos())
        self._tenant = tenant_id

    # ── acceso ──
    def _con_store[T](self, funcion: Callable[[PostgresStore], Awaitable[T]]) -> T:
        async def leer() -> T:
            async with PostgresStore(dsn=self._dsn, tenant_id=self._tenant) as store:
                return await funcion(store)

        return run_async(leer())

    def _consultar(self, sql: str, parametros: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        """Una lectura en una transacción de solo lectura."""
        with psycopg.connect(self._dsn, connect_timeout=5, options="-c search_path=radar,public") as conn:
            conn.read_only = True
            return list(conn.execute(sql, parametros).fetchall())

    # ── lectura ──
    def estado(self) -> dict[str, Any]:
        from core.orchestration.sidecar.migrations import pending_migration_names

        pendientes = pending_migration_names(self._dsn)
        resumen: dict[str, Any] = {"migraciones_pendientes": pendientes,
                                   "dossiers": len(self._almacen.listado())}
        filas = self._consultar(
            "SELECT count(*), max(started_at) FROM pipeline_runs WHERE tenant_id = %s", (self._tenant,))
        resumen["escaneos"] = int(filas[0][0])
        resumen["ultimo_escaneo"] = filas[0][1].isoformat() if filas[0][1] else None
        if not any(m.startswith("021_") for m in pendientes):
            resumen["propuestas_pendientes"] = len(self.propuestas())
        return resumen

    def nichos(self, run_id: str | None = None) -> dict[str, Any]:
        """Lo que enseña el Radar: la última ejecución con nichos o `run_id`."""
        from core.judge.store import leer_radar
        from core.orchestration.sidecar.judge import radar_para_mostrar

        if run_id is not None and not _UUID.fullmatch(run_id):
            raise DatoInvalido(f"run_id no es un id de escaneo: {run_id!r}")
        return radar_para_mostrar(self._con_store(lambda store: leer_radar(store, run_id)))

    def escaneos(self, limite: int = 20) -> list[dict[str, Any]]:
        """Los últimos escaneos guardados, del más reciente al más antiguo."""
        from core.judge.store import run_overview

        tope = max(1, min(int(limite), ESCANEOS_MAX))
        ids = [str(f[0]) for f in self._consultar(
            "SELECT id FROM pipeline_runs WHERE tenant_id = %s ORDER BY started_at DESC LIMIT %s",
            (self._tenant, tope))]

        async def leer(store: PostgresStore) -> list[dict[str, Any]]:
            return [r for r in [await run_overview(store, i) for i in ids] if r is not None]

        return self._con_store(leer)

    def escaneo(self, run_id: str) -> dict[str, Any]:
        """Un escaneo con lo que hizo cada fuente (estado, piezas, peticiones, gasto)."""
        from core.judge.store import run_overview

        if not _UUID.fullmatch(run_id):
            raise DatoInvalido(f"run_id no es un id de escaneo: {run_id!r}")
        resumen = self._con_store(lambda store: run_overview(store, run_id))
        if resumen is None:
            raise DatoInvalido(f"no hay ningún escaneo {run_id}")
        filas = self._consultar(
            "SELECT source, status, stop_reason, error_code, items, requests, units::float8, usd::float8"
            "  FROM run_source_outcomes WHERE tenant_id = %s AND run_id = %s ORDER BY source",
            (self._tenant, run_id))
        resumen["fuentes"] = [dict(zip(("fuente", "estado", "motivo_parada", "error", "piezas", "peticiones",
                                        "unidades", "usd"), f, strict=True)) for f in filas]
        return resumen

    def dossiers(self) -> list[dict[str, Any]]:
        return self._almacen.listado()

    def dossier(self, id_: str) -> str:
        """El dossier (o plan) guardado, en Markdown. Sin llamar a Gemini."""
        documento = self._almacen.por_id(id_)
        if documento is None:
            raise DatoInvalido(f"no hay ningún dossier {id_!r} (los ids salen de `dossiers`)")
        return documento.to_markdown()

    def propuestas(self) -> list[dict[str, Any]]:
        """Las propuestas que esperan a Walter en la ventana de SENTRA (la misma
        lectura que hace el motor para enseñárselas)."""
        from core.propuestas import pendientes

        return [{"id": f["id"], "perfil": f["profile"], "motivo": f["reason"], "creada": f["created_at"]}
                for f in pendientes(self._dsn, self._tenant)]

    # ── la única escritura ──
    def proponer(self, perfil: dict[str, Any], motivo: str) -> dict[str, Any]:
        """Deja una propuesta pendiente. Valida el perfil con las mismas reglas
        que el motor: una propuesta que no se podría lanzar no se guarda."""
        if len(motivo) > MOTIVO_MAX:
            raise DatoInvalido(f"el motivo pasa de {MOTIVO_MAX} caracteres")
        try:
            valido = ScanProfile.model_validate(perfil)
        except ValidationError as exc:
            errores = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'perfil'}: {e['msg']}" for e in exc.errors())
            raise DatoInvalido(f"perfil no válido: {errores}") from None
        # El asistente reparte las palabras por idioma (una fila por idioma): las
        # que Claude no marcó se deducen con la misma regla que el motor.
        valido = valido.model_copy(update={"keyword_languages": {
            p: valido.keyword_languages.get(p) or idioma_de(p) for p in valido.keywords}})
        with psycopg.connect(self._dsn, connect_timeout=5, options="-c search_path=radar,public") as conn:
            fila = conn.execute(
                "INSERT INTO scan_requests (tenant_id, profile, reason) VALUES (%s, %s::jsonb, %s)"
                " RETURNING id::text, created_at",
                (self._tenant, json.dumps(valido.model_dump(mode="json"), ensure_ascii=False), motivo),
            ).fetchone()
        assert fila is not None
        return {"id": fila[0], "estado": "pendiente", "creada": fila[1].isoformat(), "perfil": valido.name}
