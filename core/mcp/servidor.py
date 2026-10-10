"""
Servidor MCP de SENTRA (Claude Desktop)
=======================================

Como el de D&S Factory: JSON-RPC 2.0 por stdio, solo con la stdlib. El
núcleo es `ServidorMCP.manejar(peticion) -> respuesta`, puro y testeable en
memoria; `main()` solo lo conecta a stdin/stdout.

- **Lectura** (`estado`, `nichos`, `escaneos`, `escaneo`, `dossiers`,
  `dossier`, `propuestas`): la base y la carpeta de dossiers, con SENTRA
  abierta o cerrada. Nunca llama a Gemini ni a las fuentes.
- **Proponer un escaneo** (`proponer_escaneo`): deja la propuesta pendiente y
  no gasta nada. SENTRA la enseña con su estimación de siempre y el escaneo
  solo arranca si Walter pulsa «Lanzar» en la ventana (decisión del
  2026-10-09). Ninguna herramienta puede lanzar, confirmar ni descartar.

Registro en Claude Desktop (`~/.config/Claude/claude_desktop_config.json`):
``.venv/bin/python -m core.mcp.servidor`` con `PYTHONPATH` en la raíz del repo.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Protocol

import psycopg

from core.mcp.datos import ESCANEOS_MAX, MOTIVO_MAX, DatoInvalido

PROTOCOLO = "2025-06-18"
VERSION = "0.1.0"

_SOLO_LECTURA = {"readOnlyHint": True, "openWorldHint": False}
_RUN_ID = {"type": "string", "description": "Id del escaneo (uuid), de `escaneos`."}

HERRAMIENTAS: list[dict[str, Any]] = [
    {
        "name": "estado",
        "description": "Resumen de SENTRA: cuántos escaneos, el último, dossiers guardados, propuestas "
                       "pendientes y migraciones sin aplicar. Solo lectura.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"title": "Estado de SENTRA", **_SOLO_LECTURA},
    },
    {
        "name": "nichos",
        "description": "Los nichos del Radar (veredictos del juez con su evidencia, sin identificadores de "
                       "autores): los del último escaneo con nichos o los de `run_id`. Solo lectura.",
        "inputSchema": {"type": "object", "properties": {"run_id": _RUN_ID}, "additionalProperties": False},
        "annotations": {"title": "Nichos del Radar", **_SOLO_LECTURA},
    },
    {
        "name": "escaneos",
        "description": "Los últimos escaneos guardados: tema, fecha, piezas, veredictos, nichos y por qué "
                       "se pararon. Solo lectura.",
        "inputSchema": {"type": "object", "properties": {
            "limite": {"type": "integer", "minimum": 1, "maximum": ESCANEOS_MAX, "default": 20}},
            "additionalProperties": False},
        "annotations": {"title": "Escaneos", **_SOLO_LECTURA},
    },
    {
        "name": "escaneo",
        "description": "Un escaneo con lo que hizo cada fuente (estado, piezas, peticiones, gasto). "
                       "Solo lectura.",
        "inputSchema": {"type": "object", "properties": {"run_id": _RUN_ID}, "required": ["run_id"],
                        "additionalProperties": False},
        "annotations": {"title": "Detalle de un escaneo", **_SOLO_LECTURA},
    },
    {
        "name": "dossiers",
        "description": "Los dossiers y planes ya generados (id, título, veredicto, idioma, fecha). "
                       "Solo lectura.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"title": "Dossiers guardados", **_SOLO_LECTURA},
    },
    {
        "name": "dossier",
        "description": "Un dossier o plan guardado, en Markdown. No genera nada ni llama a Gemini. "
                       "Solo lectura.",
        "inputSchema": {"type": "object", "properties": {
            "id": {"type": "string", "description": "Id del dossier, de `dossiers`."}},
            "required": ["id"], "additionalProperties": False},
        "annotations": {"title": "Leer un dossier", **_SOLO_LECTURA},
    },
    {
        "name": "propuestas",
        "description": "Las propuestas de escaneo que esperan a Walter en la ventana de SENTRA. "
                       "Solo lectura.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"title": "Propuestas pendientes", **_SOLO_LECTURA},
    },
    {
        "name": "proponer_escaneo",
        "description": (
            "Propone un escaneo. NO lo lanza ni gasta nada: deja la propuesta pendiente y SENTRA se la "
            "enseña a Walter con la estimación de gasto; solo se lanza si él pulsa «Lanzar» en la ventana "
            "de SENTRA. `perfil` es el de un escaneo de SENTRA: `name`, `topic` (la frase del tema), "
            "`keywords` (términos de 1 a 3 palabras; o `discovery: true` sin palabras) y, opcionales, "
            "`keyword_languages` ({palabra: \"es\"|\"en\"}), `languages` ([\"es\", \"en\"]), "
            "`window_days` (90, 180 o 365) y `targets.stackexchange` (sitios). Walter puede cambiarla "
            "antes de lanzarla. Dile que abra SENTRA para revisarla."
        ),
        "inputSchema": {"type": "object", "properties": {
            "perfil": {"type": "object", "description": "Perfil del escaneo (como lo arma el asistente)."},
            "motivo": {"type": "string", "maxLength": MOTIVO_MAX,
                       "description": "Por qué lo propones, en una o dos frases para Walter."}},
            "required": ["perfil", "motivo"], "additionalProperties": False},
        "annotations": {"title": "Proponer un escaneo (lo lanza Walter)", "readOnlyHint": False,
                        "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
    },
]


class Datos(Protocol):
    def estado(self) -> dict[str, Any]: ...
    def nichos(self, run_id: str | None = None) -> dict[str, Any]: ...
    def escaneos(self, limite: int = 20) -> list[dict[str, Any]]: ...
    def escaneo(self, run_id: str) -> dict[str, Any]: ...
    def dossiers(self) -> list[dict[str, Any]]: ...
    def dossier(self, id_: str) -> str: ...
    def propuestas(self) -> list[dict[str, Any]]: ...
    def proponer(self, perfil: dict[str, Any], motivo: str) -> dict[str, Any]: ...


def _ok(id_: Any, resultado: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": resultado}


def _error(id_: Any, codigo: int, mensaje: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": codigo, "message": mensaje}}


def _contenido(carga: Any, *, es_error: bool = False) -> dict[str, Any]:
    texto = carga if isinstance(carga, str) else json.dumps(carga, ensure_ascii=False, indent=2, default=str)
    return {"content": [{"type": "text", "text": texto}], "isError": es_error}


class ServidorMCP:
    def __init__(self, datos: Datos) -> None:
        self._datos = datos

    def manejar(self, peticion: dict[str, Any]) -> dict[str, Any] | None:
        """La respuesta a una petición JSON-RPC (None si es una notificación)."""
        metodo = peticion.get("method")
        id_ = peticion.get("id")
        if metodo == "initialize":
            return _ok(id_, {"protocolVersion": PROTOCOLO, "capabilities": {"tools": {}},
                             "serverInfo": {"name": "sentra", "version": VERSION}})
        if isinstance(metodo, str) and metodo.startswith("notifications/"):
            return None
        if metodo == "ping":
            return _ok(id_, {})
        if metodo == "tools/list":
            return _ok(id_, {"tools": HERRAMIENTAS})
        if metodo == "tools/call":
            return self._llamar(id_, peticion.get("params") or {})
        return _error(id_, -32601, f"Método no soportado: {metodo}")

    def _llamar(self, id_: Any, params: dict[str, Any]) -> dict[str, Any]:
        nombre = params.get("name")
        args = params.get("arguments") or {}
        lectores: dict[str, Any] = {
            "estado": lambda: self._datos.estado(),
            "nichos": lambda: self._datos.nichos(args.get("run_id")),
            "escaneos": lambda: self._datos.escaneos(int(args.get("limite", 20))),
            "escaneo": lambda: self._datos.escaneo(str(args.get("run_id", ""))),
            "dossiers": lambda: self._datos.dossiers(),
            "dossier": lambda: self._datos.dossier(str(args.get("id", ""))),
            "propuestas": lambda: self._datos.propuestas(),
            "proponer_escaneo": lambda: self._proponer(args),
        }
        if nombre not in lectores:
            return _error(id_, -32602, f"Herramienta desconocida: {nombre}")
        try:
            return _ok(id_, _contenido(lectores[nombre]()))
        except (DatoInvalido, TypeError, ValueError) as exc:
            return _ok(id_, _contenido({"error": str(exc)}, es_error=True))
        except psycopg.errors.UndefinedTable:
            return _ok(id_, _contenido({"error": "A la base le faltan migraciones de SENTRA: avisa a Walter "
                                                 "(scripts/migrate.py up)."}, es_error=True))
        except psycopg.OperationalError as exc:
            return _ok(id_, _contenido({"error": f"No se pudo leer la base de SENTRA (¿PostgreSQL parado?): "
                                                 f"{type(exc).__name__}"}, es_error=True))

    def _proponer(self, args: dict[str, Any]) -> dict[str, Any]:
        perfil = args.get("perfil")
        if not isinstance(perfil, dict):
            raise DatoInvalido("`perfil` tiene que ser un objeto")
        hecho = self._datos.proponer(perfil, str(args.get("motivo") or ""))
        hecho["siguiente_paso"] = ("Pendiente: Walter la revisa en la ventana de SENTRA, ve la estimación de "
                                   "gasto y decide si la lanza. Nada se ha escaneado ni gastado.")
        return hecho


def main() -> int:
    # stdout es el canal del protocolo: los avisos de las librerías van a stderr.
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    from core.mcp.datos import DatosSentra

    servidor = ServidorMCP(DatosSentra())
    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        try:
            peticion = json.loads(linea)
        except json.JSONDecodeError:
            respuesta: dict[str, Any] | None = _error(None, -32700, "JSON no válido")
        else:
            try:
                respuesta = servidor.manejar(peticion) if isinstance(peticion, dict) else \
                    _error(None, -32600, "La petición tiene que ser un objeto")
            # Una petición no puede tumbar el servidor: el fallo inesperado es un
            # error JSON-RPC de esa petición y el bucle sigue.
            except Exception as exc:  # noqa: BLE001
                respuesta = _error(peticion.get("id"), -32603, f"Error interno: {type(exc).__name__}: {exc}")
        if respuesta is not None:
            sys.stdout.write(json.dumps(respuesta, ensure_ascii=False, default=str) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
