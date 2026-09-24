# SENTRA

Escucha el mercado antes de construir. SENTRA es una aplicación de escritorio
(Tauri + React) con un motor en Python. Reúne quejas y necesidades reales de
varias fuentes con API oficial (Hacker News, Stack Exchange, Discourse,
GitHub, Bluesky, YouTube, Mastodon, Product Hunt…), las agrupa por problema y
emite un veredicto por nicho: **CONSTRUIR**, **INVESTIGAR MÁS** o
**DESCARTAR**. Cada veredicto lleva sus compuertas, sus dimensiones y la
evidencia con atribución.

Reglas que no se negocian:

- solo APIs oficiales, sin scraping;
- ningún autor en claro (se guarda un hash salado);
- nada inventado: lo que no se sabe se dice.

## Piezas

| Pieza | Dónde | Qué hace |
|---|---|---|
| Interfaz | `ui/src` | React 19 + TypeScript: Radar, Búsqueda, Fuentes y Ajustes |
| Escritorio | `ui/src-tauri` | Tauri 2 (Rust): comandos IPC, arranque del motor, salud |
| Motor | `core/` | FastAPI en loopback con token: fuentes, escaneo multifuente, juez, búsqueda y Gemini |
| Datos | PostgreSQL 18 (`sql/migrations`) + LanceDB (`data/lancedb`, vectores e5) | Evidencia, ejecuciones, veredictos |

La pipeline antigua de Reddit se retiró. Qué se quitó y qué se conserva está
en `docs/pipeline-antigua.md`.

## Puesta en marcha (Windows)

1. **Python 3.12** en una venv propia, con las dependencias fijadas:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1 -Dev
   ```

2. **PostgreSQL 18** en local. Se crea la base `reddit_intelligence_radar` y
   se aplican las migraciones, primero en seco:

   ```powershell
   .venv\Scripts\python scripts\migrate.py up --dry-run
   .venv\Scripts\python scripts\migrate.py up
   ```

   Antes de migrar una base con datos, haz una copia con
   `pg_dump -Fc … > copia.dump`.

3. **Configuración.** Copia `.env.example` a `.env`. Las credenciales de cada
   fuente y la clave de Gemini se introducen desde la aplicación (Fuentes y
   Ajustes) y nunca se muestran de vuelta.

4. **Interfaz.**

   ```powershell
   cd ui
   npm ci
   npm run tauri dev      # desarrollo
   npm run tauri build    # release
   ```

## Calidad: la compuerta

El proyecto no tiene CI remota (D-C8). La compuerta local cumple ese papel y
un cambio no se da por bueno si alguna de estas herramientas falla o avisa:

```powershell
ruff check --no-cache                          # lint de Python
mypy                                           # tipos: core, scripts y tests (check_untyped_defs)
python -m unittest discover -s tests           # suite de Python
cd ui; npx --no-install tsc --noEmit -p .      # tipos de la interfaz (hace de lint)
cd ui; npm test                                # lógica pura de la interfaz (node --test, sin dependencias)
cd ui/src-tauri; cargo test                    # suite de Rust
cd ui/src-tauri; cargo clippy --all-targets -- -D warnings
```

`npm run build` también falla si algún chunk supera 500 kB (el límite no se
sube: se divide el código). En la interfaz no hay eslint ni prettier: serían
dependencias nuevas, y `tsc` estricto cubre el lint de tipos.

Varios tests hacen de guardia: vigilan la superficie IPC, las rutas del
sidecar, las dependencias declaradas, los contratos Python/Rust→TypeScript,
el nombre del proyecto, los tearDown y los directorios temporales. Los que
necesitan PostgreSQL se saltan si no hay servidor (`tests/_postgres.py`).

## Antes de cada release: la prueba de humo

Los tests no abren la aplicación; la prueba de humo sí (AUD2-004). Con la
release compilada con `npm run tauri build` (un `cargo build --release` suelto
deja en el mismo sitio un exe sin la interfaz embebida, que abre el servidor
de desarrollo y queda en blanco; la prueba lo detecta) y SENTRA cerrada:

```powershell
python -m tests.humo_exe          # --exe RUTA para otro ejecutable
```

Lanza `sentra.exe`, espera al motor, comprueba que Radar, Búsqueda, Fuentes y
Configuración pintan lo que dice la base (leída en solo lectura), que no hay
excepciones ni errores de CSP, que el cierre normal no deja motores y que,
matando la aplicación de golpe, el motor termina solo y libera el puerto. No
genera texto con Gemini ni consulta fuentes, y no pulsa ningún botón (uno
genera documentos). Al abrir Configuración, el motor pide a Google la lista de
modelos solo si la guardada tiene más de un día (AUD2-019). Falla si cambian
las preferencias del usuario. Tarda ~40 s; la compuerta local la ejecuta con `HUMO=1`. Una release
no se da por buena sin `HUMO OK`.

## Documentación

- `tasks/SPEC-cierre-y-documentos.md` y `tasks/SPEC-multifuente.md`:
  especificación y decisiones (D-M*, D-C*).
- `docs/pipeline-antigua.md`: qué se retiró de la pipeline antigua y qué queda.
- `docs/ARQUITECTURA_POSTGRES_Y_FRONTEND.md`: esquema y frontend (histórico,
  de la fase 6).
