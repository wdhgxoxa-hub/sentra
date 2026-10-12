# Decisiones de SENTRA (registro corto)

Las decisiones de producto y del juez siguen en `tasks/SPEC-*.md` (D-M*, D-C*) y en
`CLAUDE.md`. Aquí van las de infraestructura de la máquina, más nuevas.

## 2026-10-11 · Fase 2 de David: la base pasa a un contenedor (`sentra-pg`)

- **Qué.** La base `reddit_intelligence_radar` se copia a un Postgres 18.6 propio en
  Podman sin administrador: contenedor `sentra-pg`, `127.0.0.1:5438`, volumen
  `sentra-pg-datos`, red interna `sentra`. Los Quadlets viven en `deploy/contenedores/`
  y en `~/.config/containers/systemd/` solo hay enlaces (plantilla del agente A,
  `~/Proyectos/contenedores`). Imagen oficial por digest; clave del superusuario en
  el secreto de podman `sentra-pg-postgres` (nace en el llavero, nunca en git).
- **Por qué.** Hoy SENTRA comparte el Postgres nativo con D&S Factory y tiene que
  turnarse con sus tests (CLAUDE.md, «D&S Factory comparte PostgreSQL»). Con su propio
  contenedor cada uno va por su lado.
- **Solo la base.** La ventana (Tauri), el motor (hijo de la ventana, con token por
  arranque) y el MCP (lo lanza Claude Desktop) se quedan nativos.
- **Collation.** `C.UTF-8` con libc, como la base nativa (medido en solo lectura:
  `datcollate = datctype = C.UTF-8`, `datlocprovider = c`, UTF8).
- **Rol lector nuevo.** `sentra_lector` (NOLOGIN, sin contraseña) con SELECT en todo y
  `ALTER DEFAULT PRIVILEGES` de `sentra_owner`: para respaldos y, más adelante, el MCP.
- **Roles con la clave de hoy.** `sentra_owner` y `sentra_pruebas` los copia David con
  `copiar-roles-nativos` (viaja el hash scram, nadie ve la clave). Hasta entonces
  `sentra_owner` está NOLOGIN en el contenedor y la app sigue en el nativo.
- **Rama.** CLAUDE.md dice que la migración a Linux está en `fase-linux/migracion`,
  pero la rama activa y al día es `main`; por decisión de David estos commits van a
  `main`.
- **Vuelta atrás.** La base nativa queda intacta 7 días. Mientras la configuración no
  apunte al 5438, todo va al 5432 como antes; `systemctl --user stop sentra-pg` para el contenedor sin perder datos.

## 2026-10-11 · `RIR_PG_PORT`: el puerto se elige sin tocar el código

- `RIR_PG_URL` no basta para mover la app a otro puerto: sqlx (Rust) no lee el pgpass,
  así que una URL sin contraseña deja la ventana sin base. `RIR_PG_PORT` cambia solo
  el puerto del DSN por defecto en Python (`core/storage/postgres_store.py::puerto_pg`)
  y en Rust (`ui/src-tauri/src/db.rs::puerto_desde`), y en los tests
  (`tests/_postgres.py`, `tests/_base_real.py`). La contraseña sigue saliendo del
  pgpass de SENTRA, de la línea de ese puerto. Sin la variable o con un valor que no es
  puerto: 5432 (con aviso). Pruebas: `tests/test_puerto_pg.py` y las de `db.rs`.

## 2026-10-11 · `TimeoutStopSec=70` en `sentra-pg`

- Tras el apagón del 11-10: podman da 60 s a Postgres para pararse (`StopTimeout=60`),
  pero systemd de usuario solo esperaba 10 s (`TimeoutStopUSec=10s`, medido) y con carga
  podía matarlo a medias al apagar. Ahora `[Service] TimeoutStopSec=70` (60 s + margen).
  Se aplica con `systemctl --user daemon-reload`, sin reiniciar el contenedor.

## 2026-10-12 · `httpx2` para el TestClient y lock con hashes

- **Aviso.** Cada suite imprimía `StarletteDeprecationWarning: Using httpx with
  starlette.testclient is deprecated; install httpx2 instead`. Starlette 1.7.0 (la
  instalada, con fastapi 0.141.1) busca primero `httpx2` y, si no está, usa `httpx` y
  avisa (`starlette/testclient.py`; su extra `full` ya pide `httpx2>=2.0.0`). No venía
  de la actualización del sistema: el `.venv` es del 09-10.
- **Arreglo.** Se instala lo que pide el aviso, sin subir starlette ni fastapi:
  `httpx2==2.13.1` (de pydantic, 23-09-2026) en `requirements-dev.txt`, solo para
  pruebas. Trae `httpcore2==2.13.1` y `truststore==0.10.4`. El código de producción
  sigue con `httpx` (`requirements.txt`). Las pruebas con TestClient pasan igual.
- **Lock con hashes.** El repo no tenía lock: `requirements-lock.txt` es el `.venv`
  entero (89 paquetes, directos e indirectos) con versión exacta y sus sha256 de PyPI,
  generado con `uv pip compile --generate-hashes` fijando lo ya instalado (solo entran
  nuevos los 3 de arriba). Se instala con `--require-hashes` (README).
  `tests/test_requirements.py` exige que todo tenga hash, que coincida con los dos
  requirements y con lo instalado, y que `fastapi.testclient` se importe sin avisos
  (`python -W error`). Es de Linux x86_64 y Python 3.12.

## 2026-10-12 · Caché de modelos de fastembed traída de Windows

- **Aviso.** Cada carga del modelo decía `fastembed … Local file sizes do not match the
  metadata` (loguru, no `warnings`). **Causa:** fastembed 0.8.0 guarda junto a cada modelo
  `files_metadata.json` con la ruta y el tamaño de cada archivo, y en Windows las
  escribió con «\» (`snapshots\<revisión>\config.json`). En Linux esa ruta es un solo
  nombre que no existe y su comprobación sin red da «no cuadra» aunque los archivos
  estén bien. No era descarga a medias ni otra ruta ni otra versión: los 11 archivos de
  los dos modelos (bge-small y e5, 2,2 GB) cuadran en tamaño y en sha256 / id de git con
  el árbol que guardó huggingface_hub (`trees/<revisión>.json`).
- **Arreglo reproducible.** `python -m scripts.reparar_cache_modelos` (`--en-seco` para
  verlo): comprueba cada archivo contra ese árbol y, solo si todo cuadra, reescribe las
  rutas con «/». No descarga ni toca los modelos. El metadato viejo va a la papelera
  (`gio trash`; sin gio, se queda al lado como `.windows`). Si algo no cuadra, no toca
  nada y sale con 1: ese modelo hay que volver a descargarlo. Aplicado en esta máquina
  el 12-10 (los dos modelos).
- **Guardia.** `tests/test_storage.py` escucha el registro de fastembed mientras carga el
  modelo de la caché real y falla si avisa. Pruebas del script en
  `tests/test_reparar_cache_modelos.py`.

## 2026-10-12 · La compuerta corre los tests de Python con `-W error`

- **Por qué.** La regla es 0 avisos, pero `unittest` imprime los avisos y da OK igual:
  los dos de arriba pasaron días en verde. Ahora el paso `python` es
  `"$PY" -W error -m unittest discover -s tests`: cualquier aviso de Python
  (DeprecationWarning, el de Starlette…) es un error y la compuerta falla.
  `tests/test_compuerta.py` vigila que el paso lleve `-W error`.
- **Límite.** Los avisos que una biblioteca saca por su propio registro (fastembed usa
  loguru) no pasan por `warnings`: se vigilan en su test (`tests/test_storage.py`). Las
  líneas `WARNING:` de `logging` que salen en la suite son de pruebas que las provocan
  a propósito (token, variables mal puestas), salvo la de asyncio «Executing … took
  0.1xx seconds»: `IsolatedAsyncioTestCase` activa el modo depuración de asyncio y
  avisa si un paso tarda más de 0,1 s. Sale en
  `test_source_youtube::test_no_gasta_mas_unidades_que_el_escaneo_1` (0,11–0,12 s medidos
  el 12-10 con la máquina cargada, carga ~9): probablemente porque con `httpx.MockTransport`
  no hay red que esperar y el escaneo entero corre de un tirón (sin comprobar a fondo). No es un aviso de Python ni de
  una biblioteca y no se ha tocado: queda para decidir (aligerar esa prueba o subir el
  umbral solo en ella, con su motivo).
