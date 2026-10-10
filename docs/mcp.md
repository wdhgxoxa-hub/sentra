# SENTRA en Claude Desktop (servidor MCP)

Claude Desktop puede **leer** SENTRA y **proponer** escaneos. No puede lanzar
ni gastar nada: cada escaneo lo lanza Walter desde la ventana de SENTRA
(decisión del 2026-10-09).

## Cómo funciona

- El servidor es `core/mcp/servidor.py` (JSON-RPC por stdio, solo la stdlib,
  como el de D&S Factory). Lee la base y la carpeta de dossiers
  (`core/mcp/datos.py`), así que funciona **con SENTRA cerrada**. No habla con
  el motor (su token sigue siendo solo de la ventana, D-B), ni con Gemini ni
  con las fuentes.
- Una propuesta queda en `radar.scan_requests` (migración 021) como
  `pendiente`. La pantalla «Nuevo escaneo» la enseña con su motivo:
  - **Descartar** la marca como `descartada`.
  - **Revisar** la lleva al paso «Revisar y escanear»: se ve lo que costará
    y se puede cambiar todo. Solo **Escanear** la lanza, con la estimación
    confirmada como cualquier escaneo; el motor la marca entonces como
    `lanzada`, con su ejecución.

## Herramientas

| Herramienta | Qué hace |
|---|---|
| `estado` | Escaneos guardados, el último, dossiers, propuestas pendientes y migraciones sin aplicar |
| `nichos` | El Radar (última ejecución con nichos, o `run_id`), sin identificadores de autores (R9) |
| `escaneos` | Los últimos escaneos (`limite`, hasta 50) |
| `escaneo` | Un escaneo con lo que hizo cada fuente (piezas, peticiones, gasto, motivo de parada) |
| `dossiers` / `dossier` | Los dossiers y planes ya generados; uno en Markdown, sin llamar a Gemini |
| `propuestas` | Las propuestas pendientes |
| `proponer_escaneo` | Deja una propuesta (`perfil` y `motivo`); valida el perfil con las reglas del motor |

El perfil de una propuesta usa `name`, `topic`, `keywords` (o
`discovery: true`), `keyword_languages`, `languages`, `window_days` (el
asistente lo ajusta a 90, 180 o 365) y `targets.stackexchange`. Las palabras
sin idioma se deducen como en el motor (`idioma_de`).

## Registro

En `~/.config/Claude/claude_desktop_config.json`, junto a `dsfactory`:

```json
"sentra": {
  "command": "/home/david/SENTRA/reddit_intelligence_radar/.venv/bin/python",
  "args": ["-m", "core.mcp.servidor"],
  "env": { "PYTHONPATH": "/home/david/SENTRA/reddit_intelligence_radar" }
}
```

La base se resuelve como en el motor: `RIR_PG_URL` o `sentra_owner` con el
pgpass de SENTRA. Tras cambiar el registro hay que reiniciar Claude Desktop.

Prueba a mano (solo lectura):

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"estado","arguments":{}}}' \
  | PGOPTIONS="-c default_transaction_read_only=on" .venv/bin/python -m core.mcp.servidor
```
